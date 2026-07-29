import os
import subprocess
import shutil
import requests
import zipfile
import winreg
import ctypes
import ftplib
from urllib.parse import urlparse
import datetime

# --- Constantes de Configuração ---
DIRETORIO_APP_DATA = r"C:\ProgramData\Suporte-Cercomp"
DIRETORIO_LOGS = os.path.join(DIRETORIO_APP_DATA, "logs")
ARQUIVO_CONFIG = os.path.join(DIRETORIO_APP_DATA, "config.json")
CAMINHO_SCRIPT_WIDGET = os.path.join(DIRETORIO_APP_DATA, "AvisoDesktop.pyw")
DIRETORIO_PYTHON_WIDGET = os.path.join(DIRETORIO_APP_DATA, "python_widget_env")
REGISTRO_WIDGET = r"Software\Microsoft\Windows\CurrentVersion\Run"
CHAVE_REGISTRO_WIDGET = "FCT_UFG_DesktopInfo"
FTP_ANTIVIRUS_APEX = "ftp://ftp.suporte.cercomp.ufg.br/Antivirus 2025/TMStandardAgent_Windows_x86_64_Windows"

# ... (O CONTEUDO_SCRIPT_WIDGET permanece o mesmo) ...
CONTEUDO_SCRIPT_WIDGET = """
# Aviso Desktop
import sys
import socket
try:
    from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QGraphicsDropShadowEffect
    from PyQt6.QtCore import Qt, QEvent, QTimer
    from PyQt6.QtGui import QColor
except ImportError:
    sys.exit()

class WidgetInfo(QWidget):
    def __init__(self):
        super().__init__()
        self.configurar_interface()

    def configurar_interface(self):
        self.setWindowTitle("WidgetInfo")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnBottomHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.rotulo = QLabel(self)
        self.rotulo.setText(self.formatar_texto())
        self.rotulo.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.rotulo.setStyleSheet("QLabel { color: white; font-size: 11pt; }")
        sombra = QGraphicsDropShadowEffect(self)
        sombra.setBlurRadius(5)
        sombra.setOffset(2, 2)
        sombra.setColor(QColor(0, 0, 0))
        self.rotulo.setGraphicsEffect(sombra)
        layout = QVBoxLayout(self)
        layout.addWidget(self.rotulo)
        layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(layout)
        self.adjustSize()
        self.posicionar_widget()

    def formatar_texto(self):
        nome_computador = socket.gethostname()
        texto = (
            "<p style='margin:0; text-align:right; color:white;'>"
            "<b>💻 LAB. DE INFORMÁTICA - FCT/UFG</b><br>"
            "───────────────────────────<br>"
            f"{nome_computador}<br><br>"
            "<b>📜 REGRAS DE USO</b><br>"
            "🎓 Uso exclusivo para atividades acadêmicas<br>"
            "🚫 Não consumir alimentos no laboratório<br>"
            "⚙️ Não alterar configurações do sistema<br><br>"
            "<b>🚪 PROCEDIMENTOS AO SAIR</b><br>"
            "💾 Remova dispositivos externos<br>"
            "❌ Encerre todos os aplicativos<br>"
            "🔒 Faça logout das contas<br><br>"
            "<b>🛠️ SUPORTE TÉCNICO</b><br>"
            "🌐 chamado.ufg.br<br>"
            "💬 (62) 3209-6555"
            "</p>"
        )
        return texto

    def posicionar_widget(self):
        tela = QApplication.primaryScreen()
        if tela:
            retangulo_disponivel = tela.availableGeometry()
            margem = 20
            x = retangulo_disponivel.right() - self.width() - margem
            y = retangulo_disponivel.top() + margem
            self.move(x, y)

    def changeEvent(self, evento):
        if evento.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                QTimer.singleShot(0, self.showNormal)
        super().changeEvent(evento)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = WidgetInfo()
    widget.show()
    sys.exit(app.exec())
"""

def executar_comando_powershell(comando, timeout=180):
    """Executa um comando PowerShell."""
    yield f"Executando via PowerShell: {comando[:70]}..."
    try:
        processo = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", comando],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=timeout, check=False
        )
        if processo.stdout:
            yield processo.stdout.strip()
        if processo.returncode != 0:
            yield f"⚠️ ERRO: Código de retorno {processo.returncode}."
            if processo.stderr:
                yield f"Detalhes: {processo.stderr.strip()}"
    except Exception as e:
        yield f"⚠️ ERRO CRÍTICO (PowerShell): {e}"

def executar_comando_cmd(comando, timeout=180, work_dir=None):
    """Executa um comando no CMD, com opção de diretório de trabalho."""
    yield f"Executando via CMD: {comando[:70]}..."
    try:
        processo = subprocess.run(
            ["cmd", "/c", comando],
            capture_output=True, text=True, encoding='oem', errors='ignore',
            timeout=timeout, check=False, cwd=work_dir,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if processo.stdout:
            yield processo.stdout.strip()
        if processo.returncode != 0:
            yield f"AVISO: Código de retorno {processo.returncode}."
            if processo.stderr:
                yield f"Saída de erro: {processo.stderr.strip()}"
    except Exception as e:
        yield f"⚠️ ERRO CRÍTICO (CMD): {e}"

def _listar_usuarios_padrao():
    """
    Retorna a lista de usuários LOCAIS 'padrão' (isto é, que NÃO pertencem ao grupo de Administradores)
    """
    # Contas internas do Windows que nunca devem ser tratadas como "aluno".
    contas_sistema = "'Administrador','Administrator','Convidado','Guest','DefaultAccount','WDAGUtilityAccount','defaultuser0', 'Suporte - Cercomp', 'Suporte_Cercomp', 'Suporte-Cercomp'"


    comando_ps = (
        "$grupoAdmins = Get-LocalGroup | Where-Object { $_.SID -like '*-544' }; "
        "$membrosAdmins = @(); "
        "if ($grupoAdmins) { "
        "$membrosAdmins = @((Get-LocalGroupMember -Group $grupoAdmins -ErrorAction SilentlyContinue) | "
        "ForEach-Object { $_.Name -replace '^.*\\\\', '' }) }; "
        f"$contasSistema = @({contas_sistema}); "
        "$usuarios = Get-LocalUser -ErrorAction SilentlyContinue | Where-Object { $_.Enabled -eq $true }; "
        "$usuariosPadrao = $usuarios | Where-Object { ($membrosAdmins -notcontains $_.Name) -and ($contasSistema -notcontains $_.Name) }; "
        "($usuariosPadrao.Name) -join ';'"
    )

    try:
        processo = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", comando_ps],
            capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=60, check=False, creationflags=subprocess.CREATE_NO_WINDOW
        )
    except Exception as e:
        return [], f"⚠️ ERRO CRÍTICO ao listar usuários locais: {e}"

    if processo.returncode != 0:
        detalhe = processo.stderr.strip() if processo.stderr else "sem detalhes adicionais"
        return [], f"⚠️ ERRO CRÍTICO ao listar usuários locais (código {processo.returncode}): {detalhe}"

    nomes_brutos = (processo.stdout or "").strip()
    if not nomes_brutos:
        return [], None

    nomes_usuarios = [n.strip() for n in nomes_brutos.split(';') if n.strip()]

    usuarios_validos = []
    for nome in nomes_usuarios:
        caminho_desktop = os.path.join("C:\\Users", nome, "Desktop")
        if os.path.exists(caminho_desktop):
            usuarios_validos.append((nome, caminho_desktop))

    return usuarios_validos, None

def reiniciar_explorer():
    """Reinicia o processo do Windows Explorer de forma segura."""
    yield "↩ Reiniciando parâmetros do sistema..."
    yield from executar_comando_cmd("RUNDLL32.EXE user32.dll,UpdatePerUserSystemParameters ,1 ,True")
    
    yield "Reiniciando o Windows Explorer..."
    comando_ps = (
        "Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue; "
        "Start-Sleep -Seconds 3; "
        "Start-Process explorer.exe"
    )
    yield from executar_comando_powershell(comando_ps)
    yield from executar_comando_cmd(r"gpupdate /force", timeout=300)
    yield "Atualização de políticas forçada."

def habilitar_escrita_desktop():
    """
    Restaura a permissão de escrita no Desktop e na pasta de Themes (wallpaper) 
    para os usuários Padrão (não administradores).
    """
    yield "🔓 Habilitando Permissão de Escrita e Troca de Wallpaper (usuários padrão) ---"
    usuarios_padrao, erro = _listar_usuarios_padrao()
    if erro:
        yield erro
        return
    if not usuarios_padrao:
        yield "AVISO: Nenhum usuário padrão (não administrador) foi encontrado neste computador."
        return

    # 1. Limpar restrições de registro no nível da MÁQUINA (HKLM) - Remove a mensagem para todos
    yield "Limpando políticas globais de máquina (HKLM)..."
    yield from executar_comando_powershell(
        'Remove-ItemProperty -Path "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\ActiveDesktop" -Name "NoChangingWallpaper" -ErrorAction SilentlyContinue; '
        'Remove-ItemProperty -Path "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System" -Name "Wallpaper" -ErrorAction SilentlyContinue'
    )

    for nome_usuario, caminho_desktop in usuarios_padrao:
        yield f"Restaurando permissões para '{nome_usuario}'..."
        
        # 2. Desbloquear Desktop
        yield from executar_comando_cmd(f'icacls "{caminho_desktop}" /remove:d "{nome_usuario}" /T /C')
        yield from executar_comando_cmd(f'icacls "{caminho_desktop}" /grant "{nome_usuario}":(F) /T /C')
        
        # 3. Desbloquear pasta Themes e CachedFiles (Onde o Windows guarda o wallpaper processado)
        caminho_themes = os.path.join("C:\\Users", nome_usuario, "AppData\\Roaming\\Microsoft\\Windows\\Themes")
        if os.path.exists(caminho_themes):
            yield from executar_comando_cmd(f'icacls "{caminho_themes}" /remove:d "{nome_usuario}" /T /C')
            yield from executar_comando_cmd(f'icacls "{caminho_themes}" /grant "{nome_usuario}":(F) /T /C')
            
            caminho_cached = os.path.join(caminho_themes, "CachedFiles")
            if os.path.exists(caminho_cached):
                yield from executar_comando_cmd(f'icacls "{caminho_cached}" /remove:d "{nome_usuario}" /T /C')
                yield from executar_comando_cmd(f'icacls "{caminho_cached}" /grant "{nome_usuario}":(F) /T /C')

        # 4. Remover bloqueio do registro no nível do USUÁRIO (HKCU)
        comando_ps = f'''
        $user = "{nome_usuario}"
        $localUser = Get-LocalUser -Name $user -ErrorAction SilentlyContinue
        if (-not $localUser) {{ return }}
        
        $sid = $localUser.SID.Value
        $hivePath = "C:\\Users\\$user\\NTUSER.DAT"
        $regPath = "Registry::HKEY_USERS\\$sid"
        $tempHive = "HKU\\TempHive_$user"
        $loaded = $false

        if (-not (Test-Path $regPath)) {{
            reg load $tempHive $hivePath 2>$null
            if (Test-Path "Registry::$tempHive") {{
                $regPath = "Registry::$tempHive"
                $loaded = $true
            }}
        }}

        if (Test-Path $regPath) {{
            $paths = @(
                "$regPath\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\ActiveDesktop",
                "$regPath\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System"
            )
            foreach ($p in $paths) {{
                if (Test-Path $p) {{
                    Remove-ItemProperty -Path $p -Name "NoChangingWallpaper" -ErrorAction SilentlyContinue
                    Remove-ItemProperty -Path $p -Name "Wallpaper" -ErrorAction SilentlyContinue
                    Remove-ItemProperty -Path $p -Name "WallpaperStyle" -ErrorAction SilentlyContinue
                }}
            }}
        }}

        if ($loaded) {{
            [gc]::Collect()
            reg unload $tempHive 2>$null
        }}
        Write-Output "Registro liberado para $user."
        '''
        yield from executar_comando_powershell(comando_ps)

    yield "Permissões HABILITADAS: Usuários padrão podem alterar o wallpaper."
    yield from reiniciar_explorer()
    
def desabilitar_escrita_desktop():
    """
    Remove a permissão de escrita no Desktop e bloqueia a alteração de wallpaper 
    SOMENTE para os usuários PADRÃO (não administradores).
    """
    yield "🔒 Desabilitando Permissão de Escrita e Troca de Wallpaper (usuários padrão) ---"
    usuarios_padrao, erro = _listar_usuarios_padrao()
    if erro:
        yield erro
        return
    if not usuarios_padrao:
        yield "AVISO: Nenhum usuário padrão (não administrador) foi encontrado neste computador. Nada a fazer."
        return

    for nome_usuario, caminho_desktop in usuarios_padrao:
        yield f"Negando permissões para o usuário padrão '{nome_usuario}'..."
        yield from executar_comando_cmd(f'icacls "{caminho_desktop}" /deny "{nome_usuario}":(W,DC) /T /C')
        caminho_themes = os.path.join("C:\\Users", nome_usuario, "AppData\\Roaming\\Microsoft\\Windows\\Themes")
        if os.path.exists(caminho_themes):
            yield from executar_comando_cmd(f'icacls "{caminho_themes}" /deny "{nome_usuario}":(W,DC) /T /C')
        comando_ps = f'''
        $user = "{nome_usuario}"
        try {{
            $sid = (New-Object System.Security.Principal.NTAccount($user)).Translate([System.Security.Principal.SecurityIdentifier]).Value
        }} catch {{
            $sid = $null
        }}
        $hiveLoaded = $false
        $basePath = "Registry::HKEY_USERS\\$sid"
        
        if (-not $sid -or -not (Test-Path $basePath)) {{
            reg load "HKU\\TempHive_$user" "C:\\Users\\$user\\NTUSER.DAT" 2>$null
            if (Test-Path "Registry::HKEY_USERS\\TempHive_$user") {{
                $hiveLoaded = $true
                $basePath = "Registry::HKEY_USERS\\TempHive_$user"
            }}
        }}
        
        if ($basePath) {{
            $keyPath = "$basePath\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\ActiveDesktop"
            if (-not (Test-Path $keyPath)) {{
                New-Item -Path $keyPath -Force | Out-Null
            }}
            Set-ItemProperty -Path $keyPath -Name "NoChangingWallpaper" -Value 1 -Type DWord
        }}
        
        if ($hiveLoaded) {{
            [gc]::Collect()
            reg unload "HKU\\TempHive_$user" 2>$null
        }}
        Write-Output "Bloqueio de registro aplicado para $user."
        '''
        yield from executar_comando_powershell(comando_ps)

    yield "Permissões DESABILITADAS: Usuários padrão não podem mais alterar o wallpaper."
    yield from reiniciar_explorer()

def baixar_recursos_necessarios(url_repositorio):
    """⬇️ Baixa os arquivos de configuração (GPOs, Tema) do GitHub."""
    arquivos_para_baixar = ["lgpo.exe", "machine.txt", "user.txt", "fct-labs.deskthemepack"]
    yield "Verificando e baixando recursos necessários..."
    
    if not url_repositorio.endswith('/'):
        url_repositorio += '/'
    
    for arquivo in arquivos_para_baixar:
        url_arquivo = url_repositorio + arquivo
        caminho_destino = os.path.join(DIRETORIO_APP_DATA, arquivo)
        
        yield f"⬇ Baixando '{arquivo}'..."
        try:
            with requests.get(url_arquivo, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(caminho_destino, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
        
            if not os.path.exists(caminho_destino) or os.path.getsize(caminho_destino) == 0:
                yield f"⚠️ ERRO: '{arquivo}' foi baixado mas está vazio ou corrompido."
                return
                
            yield f"'{arquivo}' baixado com sucesso ({os.path.getsize(caminho_destino)} bytes)."
        except requests.exceptions.RequestException as e:
            yield f"⚠️ ERRO CRÍTICO ao baixar '{arquivo}': {e}"
            return
    
    yield "Download de todos os recursos concluído."

def gerenciar_widget_desktop(acao, config):
    """Adiciona ou remove o widget de aviso do desktop."""
    pythonw_exe = os.path.join(DIRETORIO_PYTHON_WIDGET, 'pythonw.exe')
    comando_finalizar = f'taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq WidgetInfo*"'

    if acao == 'adicionar':
        url_python_widget = config.get("URL_PYTHON_WIDGET")
        if not url_python_widget:
            yield "⚠️ ERRO CRÍTICO: URL para o ambiente Python do widget não configurada."
            return
        zip_path = os.path.join(DIRETORIO_APP_DATA, "python_widget_env.zip")
        yield f"⬇ Baixando ambiente Python do widget..."
        try:
            with requests.get(url_python_widget, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(zip_path, 'wb') as f: shutil.copyfileobj(r.raw, f)
        except requests.exceptions.RequestException as e:
            yield f"⚠️ ERRO CRÍTICO ao baixar o ambiente do widget: {e}"; return
        yield "Extraindo ambiente Python..."
        try:
            if os.path.exists(DIRETORIO_PYTHON_WIDGET): shutil.rmtree(DIRETORIO_PYTHON_WIDGET)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref: zip_ref.extractall(DIRETORIO_PYTHON_WIDGET)
            os.remove(zip_path)
        except Exception as e:
            yield f"⚠️ ERRO CRÍTICO ao extrair o ambiente do widget: {e}"; return
        if not os.path.exists(pythonw_exe):
            yield f"⚠️ ERRO CRÍTICO: 'pythonw.exe' não encontrado após extração."; return
        yield "Ambiente do widget instalado."
        yield f"📜Criando script do widget..."
        with open(CAMINHO_SCRIPT_WIDGET, "w", encoding="utf-8") as f: f.write(CONTEUDO_SCRIPT_WIDGET)
        yield "Adicionando à inicialização do Windows..."
        try:
            comando_reg = f'"{pythonw_exe}" "{CAMINHO_SCRIPT_WIDGET}"'
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRO_WIDGET, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, CHAVE_REGISTRO_WIDGET, 0, winreg.REG_SZ, comando_reg)
            yield "Widget configurado para iniciar com o Windows."
        except Exception as e:
            yield f"⚠️ ERRO ao registrar na inicialização: {e}"; return
        yield "Finalizando instâncias antigas e iniciando o widget..."
        subprocess.run(comando_finalizar, shell=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        subprocess.Popen([pythonw_exe, CAMINHO_SCRIPT_WIDGET], creationflags=subprocess.CREATE_NO_WINDOW)
        yield "Widget adicionado e iniciado com sucesso."
    elif acao == 'remover':
        yield "Finalizando processo do widget..."
        subprocess.run(comando_finalizar, shell=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        yield "Removendo da inicialização do Windows..."
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRO_WIDGET, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, CHAVE_REGISTRO_WIDGET)
            yield "Registro de inicialização removido."
        except FileNotFoundError: yield "AVISO: Registro de inicialização não encontrado."
        except Exception as e: yield f"⚠️ ERRO ao remover do registro: {e}"
        if os.path.exists(CAMINHO_SCRIPT_WIDGET):
            try: os.remove(CAMINHO_SCRIPT_WIDGET); yield "Arquivo de script removido."
            except OSError as e: yield f"⚠️ ERRO ao remover arquivo de script: {e}"
        if os.path.exists(DIRETORIO_PYTHON_WIDGET):
            try: shutil.rmtree(DIRETORIO_PYTHON_WIDGET); yield "Ambiente Python do widget removido."
            except OSError as e: yield f"⚠️ ERRO ao remover diretório do widget: {e}"
        yield "Widget removido com sucesso."

def aplicar_tema_fct(caminho_tema):
    """
    Versão alternativa que aplica o tema usando múltiplas estratégias para detectar o usuário logado.
    """
    yield "⛺ Iniciando aplicação de tema (método alternativo)..."

    # Verificar privilégios de Administrador
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        if not is_admin:
            yield "⚠️ ERRO CRÍTICO: Esta função requer privilégios de Administrador."
            return
        yield "Verificação de privilégios de Administrador: OK."
    except Exception as e:
        yield f"⚠️ ERRO ao verificar privilégios de Administrador: {e}"
        return

    # Validação do arquivo de tema
    if not os.path.exists(caminho_tema):
        yield f"⚠️ ERRO: Arquivo de tema não encontrado: {caminho_tema}."
        return
    yield f"Arquivo de tema encontrado: {os.path.basename(caminho_tema)}"

    # Múltiplas estratégias para obter usuário logado
    usuario_logado = None
    
    # Estratégia 1: Win32_ComputerSystem
    try:
        yield "Tentativa 1: Obtendo usuário via Win32_ComputerSystem..."
        comando_ps1 = "(Get-CimInstance -ClassName Win32_ComputerSystem).Username"
        processo1 = subprocess.run(
            ["powershell", "-NoProfile", "-Command", comando_ps1],
            capture_output=True, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=30
        )
        if processo1.stdout and processo1.stdout.strip():
            usuario_logado = processo1.stdout.strip()
            yield f"✓ Usuário encontrado (Método 1): {usuario_logado}"
    except Exception as e:
        yield f"Método 1 falhou: {e}"

    # Estratégia 2: query user
    if not usuario_logado:
        try:
            yield "Tentativa 2: Obtendo usuário via 'query user'..."
            processo2 = subprocess.run(
                ["query", "user"],
                capture_output=True, text=True, encoding='oem',
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=30
            )
            if processo2.stdout:
                linhas = processo2.stdout.strip().split('\n')
                for linha in linhas[1:]:  # Pular cabeçalho
                    if 'Active' in linha or 'Ativo' in linha:
                        partes = linha.split()
                        if len(partes) > 0:
                            usuario_logado = partes[0]
                            yield f"✓ Usuário encontrado (Método 2): {usuario_logado}"
                            break
        except Exception as e:
            yield f"Método 2 falhou: {e}"

    # Estratégia 3: whoami
    if not usuario_logado:
        try:
            yield "Tentativa 3: Obtendo usuário via 'whoami'..."
            processo3 = subprocess.run(
                ["whoami"],
                capture_output=True, text=True, encoding='oem',
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=30
            )
            if processo3.stdout and processo3.stdout.strip():
                whoami_result = processo3.stdout.strip()
                if '\\' in whoami_result:
                    usuario_logado = whoami_result.split('\\')[-1]
                    yield f"✓ Usuário encontrado (Método 3): {usuario_logado}"
        except Exception as e:
            yield f"Método 3 falhou: {e}"

    # Estratégia 4: Variável de ambiente
    if not usuario_logado:
        try:
            yield "Tentativa 4: Obtendo usuário via variável de ambiente..."
            usuario_env = os.environ.get('USERNAME')
            if usuario_env:
                usuario_logado = usuario_env
                yield f"✓ Usuário encontrado (Método 4): {usuario_logado}"
        except Exception as e:
            yield f"Método 4 falhou: {e}"

    # Verificar se encontrou usuário
    if not usuario_logado:
        yield "AVISO: Não foi possível determinar o usuário logado."
        yield "Tentando aplicar tema sem contexto específico de usuário..."
        
        # Aplicar tema sem usuário específico
        try:
            yield "Aplicando tema diretamente..."
            subprocess.Popen([caminho_tema], shell=True)
            yield "Tema aplicado! A janela de personalização deve abrir."
            return
        except Exception as e:
            yield f"⚠️ ERRO ao aplicar tema: {e}"
            return

    # Aplicar tema com usuário específico
    yield f"Aplicando tema para o usuário: {usuario_logado}..."
    
    # Script PowerShell mais robusto
    script_aplicar = f"""
    try {{
        # Múltiplas tentativas de aplicação
        $CaminhoTema = '{caminho_tema.replace("'", "''")}'

        Write-Output "Aguardando 5 segundos antes de aplicar..."
        Start-Sleep -Seconds 5
        
        # Método 1: Start-Process simples
        try {{
            $ProcessInfo = Start-Process -FilePath 'explorer.exe' -ArgumentList "`"$CaminhoTema`"" -PassThru -ErrorAction Stop
            Write-Output "✓ Tema aplicado via Start-Process. PID: $($ProcessInfo.Id)"
        }} catch {{
            Write-Warning "Start-Process falhou: $($_.Exception.Message)"
            
            # Método 2: Invoke-Item
            try {{
                Invoke-Item -Path $CaminhoTema -ErrorAction Stop
                Write-Output "✓ Tema aplicado via Invoke-Item"
            }} catch {{
                Write-Warning "Invoke-Item falhou: $($_.Exception.Message)"
                
                # Método 3: cmd /c start
                try {{
                    cmd /c start `"Aplicar Tema`" `"$CaminhoTema`"
                    Write-Output "✓ Tema aplicado via cmd start"
                }} catch {{
                    Write-Error "Todos os métodos falharam: $($_.Exception.Message)"
                    exit 1
                }}
            }}
        }}

        Write-Output "Aguardando 7 segundos para o sistema processar o tema..."
        Start-Sleep -Seconds 7

    }} catch {{
        Write-Error "⚠️ ERRO CRÍTICO ao aplicar tema: $($_.Exception.Message)"
        exit 1
    }}
    """
    
    resultado = list(executar_comando_powershell(script_aplicar,timeout=600))
    for linha in resultado:
        yield linha

    yield "Aplicação de tema concluída."
    yield "Se a janela 'Personalização' abrir, pode fechá-la."
    
    ps, cmd = executar_comando_powershell, executar_comando_cmd
    usuarios = ["UFG", "Aluno", "Usuário"]
    for usuario in usuarios:
        user_dir = fr"C:\Users\{usuario}"
        ntuser_path = os.path.join(user_dir, "NTUSER.DAT")

        if not os.path.exists(user_dir):
            yield f"⚠️ Usuário {usuario} não encontrado, pulando..."
            continue

        yield f"Aplicando configurações para o usuário {usuario}..."
        yield from ps(fr'reg load HKU\TempHive "{ntuser_path}"')

        # Desativar luz noturna
        comandoDesativarLuzNoturna = r"""
        $path = "HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\Cache\DefaultAccount\`$`$windows.data.bluelightreduction.bluelightreductions\Default"
        if (Test-Path $path) {
            Set-ItemProperty -Path $path -Name Data -Value ([byte[]](0x00)) -ErrorAction SilentlyContinue
        }"""
        yield "Desativando luz noturna..."
        yield from ps(comandoDesativarLuzNoturna)
        yield from ps(r'reg add "HKCU\Software\Policies\Microsoft\Windows\NightLight" /v Enabled /t REG_DWORD /d 0 /f')

        # Ajustar ícones da área de trabalho para tamanho médio
        yield "Ajustando ícones da área de trabalho para tamanho médio..."
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\Shell\Bags\1\Desktop IconSize 32')

        yield from ps(r'reg unload HKU\TempHive')
        yield f"Configurações aplicadas para o usuário {usuario}."

    yield "Definindo wallpaper para 'Ajustar'..."
    comandoWallpaperAjustar = "Set-ItemProperty -Path 'HKCU:\Control Panel\Desktop' -Name WallpaperStyle -Value 6; Set-ItemProperty -Path 'HKCU:\Control Panel\Desktop' -Name TileWallpaper -Value 0"
    yield from executar_comando_powershell(comandoWallpaperAjustar)

    yield "Definindo imagem da tela de bloqueio igual ao wallpaper..."
    comandoLockScreen = fr"""
    $wallpaper = (Get-ItemProperty -Path 'HKCU:\Control Panel\Desktop' -Name Wallpaper).Wallpaper
    Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Lock Screen" -Name Path -Value $wallpaper
    """
    yield from executar_comando_powershell(comandoLockScreen)

def aplicar_gpos_fct(caminho_base_gpo):
    """Aplica as políticas de grupo (GPOs) da FCT usando lgpo.exe."""
    arquivos_necessarios = [
        os.path.join(caminho_base_gpo, "lgpo.exe"),
        os.path.join(caminho_base_gpo, "machine.txt"),
        os.path.join(caminho_base_gpo, "user.txt")
    ]
    yield "Verificando arquivos de GPO necessários..."
    if not all(os.path.exists(p) for p in arquivos_necessarios):
        yield f"⚠️ ERRO: Arquivos de GPO não encontrados em {caminho_base_gpo}."
        return
    
    diretorio_original = os.getcwd()
    try:
        os.chdir(caminho_base_gpo)
        yield "Aplicando política de máquina..."
        yield from executar_comando_cmd(r"lgpo.exe /t machine.txt")
        yield "Aplicando política de usuário..."
        yield from executar_comando_cmd(r"lgpo.exe /t user.txt")
        yield "Comandos de aplicação de GPOs da FCT enviados."
    except Exception as e:
        yield f"⚠️ ERRO ao executar aplicação de GPO: {e}"
    finally:
        os.chdir(diretorio_original)

    # Verificação do Mesh Agent
    mesh_agent_path = r"C:\Program Files\Mesh Agent\MeshAgent.exe"
    if not os.path.exists(mesh_agent_path):
        # Exibe caixa de mensagem informando ausência do Mesh Agent
        ctypes.windll.user32.MessageBoxW(
            0,
            "O Mesh Agent não está instalado neste computador.\nPor favor, instale o Mesh Agent antes de aplicar as GPOs.",
            "Aviso - Mesh Agent",
            0x40  # Ícone de informação
        )
        yield "⚠️ ERRO: Mesh Agent não encontrado."
        

def iniciar_limpeza_sistema(url_ferramenta):
    """Baixa e executa o BleachBit para limpeza geral do sistema + limpeza manual de pastas e disco em todos os usuários padrão."""
    base_dir = DIRETORIO_APP_DATA
    tool_dir = os.path.join(base_dir, "BleachBit")
    zip_path = os.path.join(base_dir, "BleachBit.zip")
    try:
        yield f"⬇️ Baixando BleachBit para {base_dir}..."
        with requests.get(url_ferramenta, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(zip_path, 'wb') as f: shutil.copyfileobj(r.raw, f)
        yield f"📂 Extraindo para {tool_dir}..."
        if os.path.exists(tool_dir): shutil.rmtree(tool_dir)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref: zip_ref.extractall(tool_dir)
        yield "🔍 Procurando por bleachbit_console.exe..."
        caminho_executavel = next((os.path.join(r, f) for r, _, fs in os.walk(tool_dir) for f in fs if f == "bleachbit_console.exe"), None)
        if not caminho_executavel:
            yield "⚠️ ERRO: bleachbit_console.exe não encontrado após a extração."; return
        yield f"Executável encontrado: {caminho_executavel}"
        yield "🧹 Listando limpadores disponíveis..."
        list_process = subprocess.run([caminho_executavel, "--list-cleaners"], capture_output=True, text=True, check=True)
        all_cleaners = list_process.stdout.split()
        cleaners_to_run = [c for c in all_cleaners if not c.startswith("deep_scan.") and c != "system.free_disk_space"]
        yield f"{len(cleaners_to_run)} limpadores selecionados. AVISO: A limpeza pode demorar."

        yield "🧹 Executando limpeza com BleachBit..."
        subprocess.run([caminho_executavel, "--clean"] + cleaners_to_run, check=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=600)

        # Limpeza manual em todos os usuários padrão
        usuarios = ["UFG", "Aluno", "Usuário"]
        for usuario in usuarios:
            yield f"🧹 Limpando pastas do usuário {usuario}..."
            user_dir = fr"C:\Users\{usuario}"

            if not os.path.exists(user_dir):
                yield f"⚠️ Usuário {usuario} não encontrado, pulando..."
                continue

            yield from executar_comando_powershell(fr'Remove-Item -Path "{user_dir}\AppData\Local\Temp\*" -Recurse -Force -ErrorAction SilentlyContinue')
            yield from executar_comando_powershell(fr'Remove-Item -Path "{user_dir}\AppData\Roaming\Microsoft\Windows\Recent\*" -Recurse -Force -ErrorAction SilentlyContinue')
            yield from executar_comando_powershell(fr'Clear-RecycleBin -Force -ErrorAction SilentlyContinue')

        yield "🧹 Apagando arquivos das pastas Temp e Prefetch globais..."
        yield from executar_comando_powershell(r'Remove-Item -Path "C:\Windows\Temp\*" -Recurse -Force -ErrorAction SilentlyContinue')
        yield from executar_comando_powershell(r'Remove-Item -Path "C:\Windows\Prefetch\*" -Recurse -Force -ErrorAction SilentlyContinue')

        yield "Esvaziando lixeira..."
        yield from executar_comando_powershell(r"""rd /s /q C:\$Recycle.Bin""")
        yield from executar_comando_powershell(r"""Remove-Item -Path "$env:SystemDrive\$Recycle.Bin\*" -Recurse -Force -ErrorAction SilentlyContinue""")

        yield "💾 Liberando espaço em disco com Cleanmgr..."
        yield from executar_comando_cmd("cleanmgr /sagerun:1", timeout=600)

        yield from remover_aplicativos_indesejados()

        yield "✅ Limpeza completa concluída!"
    except Exception as e:
        yield f"⚠️ ERRO durante a limpeza: {e}"
    finally:
        if os.path.exists(tool_dir): shutil.rmtree(tool_dir, ignore_errors=True)
        if os.path.exists(zip_path): os.remove(zip_path)

def _verificar_antivirus_apex_instalado():
    """
    Verifica no Registro do Windows se o antivírus Apex (Trend Micro) já está instalado.
    Usa o Registro em vez de 'Get-WmiObject Win32_Product', pois essa classe WMI é
    extremamente lenta e, como efeito colateral, força uma reconfiguração (reparo)
    de todos os pacotes MSI instalados na máquina toda vez que é consultada.
    """
    caminhos_uninstall = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, caminho in caminhos_uninstall:
        try:
            with winreg.OpenKey(hive, caminho) as chave_raiz:
                indice = 0
                while True:
                    try:
                        subchave_nome = winreg.EnumKey(chave_raiz, indice)
                    except OSError:
                        break
                    indice += 1
                    try:
                        with winreg.OpenKey(chave_raiz, subchave_nome) as subchave:
                            nome_exibicao, _ = winreg.QueryValueEx(subchave, "DisplayName")
                            if nome_exibicao and "apex" in nome_exibicao.lower():
                                return True, nome_exibicao
                    except (FileNotFoundError, OSError):
                        continue
        except FileNotFoundError:
            continue
    return False, None

def _baixar_pasta_ftp(ftp, caminho_ftp, caminho_local):
    """
    Baixa recursivamente uma pasta (e subpastas) de um servidor FTP.
    """
    os.makedirs(caminho_local, exist_ok=True)
    linhas = []
    try:
        ftp.retrlines(f"LIST {caminho_ftp}", linhas.append)
    except ftplib.error_perm as e:
        yield f"⚠️ ERRO ao listar '{caminho_ftp}': {e}"
        return

    for linha in linhas:
        # Formato padrão Unix do LIST: permissões, links, dono, grupo, tamanho, mês, dia, hora/ano, nome
        partes = linha.split(maxsplit=8)
        if len(partes) < 9:
            continue
        nome = partes[8]
        if nome in (".", ".."):
            continue

        eh_pasta = linha.upper().startswith("D")
        caminho_item_ftp = f"{caminho_ftp}/{nome}"
        caminho_item_local = os.path.join(caminho_local, nome)

        if eh_pasta:
            yield f"📁 Entrando na pasta '{nome}'..."
            yield from _baixar_pasta_ftp(ftp, caminho_item_ftp, caminho_item_local)
        else:
            yield f"⬇ Baixando arquivo '{nome}'..."
            try:
                with open(caminho_item_local, "wb") as f:
                    ftp.retrbinary(f"RETR {caminho_item_ftp}", f.write)
            except Exception as e:
                yield f"⚠️ ERRO ao baixar '{nome}': {e}"

def instalar_antivirus_apex():
    """
    🛡️ Baixa (via FTP) e executa o instalador do antivírus Apex (Trend Micro)
    """
    yield "🛡️ Verificando se o antivírus Apex já está instalado..."
    ja_instalado, nome_encontrado = _verificar_antivirus_apex_instalado()
    if ja_instalado:
        yield f"✅ Antivírus já instalado ({nome_encontrado}). Instalação não será executada."
        return

    ftp_url = FTP_ANTIVIRUS_APEX
    if not ftp_url:
        yield "⚠️ ERRO CRÍTICO: URL do FTP do antivírus Apex não configurada (FTP_ANTIVIRUS_APEX)."
        return

    partes_url = urlparse(ftp_url)
    if partes_url.scheme != "ftp" or not partes_url.hostname:
        yield "⚠️ ERRO CRÍTICO: FTP_ANTIVIRUS_APEX deve estar no formato 'ftp://servidor/caminho'."
        return

    servidor_ftp = partes_url.hostname
    caminho_raiz_ftp = (partes_url.path or "/").rstrip("/")
    nome_pasta = os.path.basename(caminho_raiz_ftp) or "TMStandardAgent"
    destino_raiz = os.path.join(DIRETORIO_APP_DATA, nome_pasta)
    caminho_exe = os.path.join(destino_raiz, "EndpointBasecamp.exe")

    yield f"📡 Conectando ao servidor FTP '{servidor_ftp}'..."
    try:
        ftp = ftplib.FTP(servidor_ftp, timeout=60)
        ftp.login()  # login anônimo, como no script original
    except Exception as e:
        yield f"⚠️ ERRO CRÍTICO ao conectar ao FTP: {e}"
        return

    try:
        yield "⬇️ Iniciando download dos arquivos do antivírus..."
        yield from _baixar_pasta_ftp(ftp, caminho_raiz_ftp, destino_raiz)
        yield "Download concluído."
    finally:
        try:
            ftp.quit()
        except Exception:
            pass

    if not os.path.exists(caminho_exe):
        yield f"⚠️ ERRO CRÍTICO: 'EndpointBasecamp.exe' não encontrado em '{destino_raiz}'."
        return

    yield "🚀 Executando o instalador do antivírus Apex..."
    try:
        subprocess.Popen([caminho_exe], cwd=destino_raiz)
        yield "Instalador iniciado com sucesso."
    except Exception as e:
        yield f"⚠️ ERRO CRÍTICO ao executar o instalador: {e}"

def renomear_computador(novo_nome):
    """Altera o nome do computador no sistema."""
    yield f"💻Tentando alterar o nome para '{novo_nome}'..."
    yield from executar_comando_powershell(f'Rename-Computer -NewName "{novo_nome}" -Force -ErrorAction Stop')
    yield "Nome alterado! É necessário reiniciar para aplicar."

def restaurar_gpos_padrao():
    """Remove as políticas locais e força a atualização."""
    caminhos_gpo = [
        os.path.join(os.environ['WINDIR'], 'System32', 'GroupPolicy'),
        os.path.join(os.environ['WINDIR'], 'System32', 'GroupPolicyUsers')
    ]
    for path in caminhos_gpo:
        if os.path.exists(path):
            try:
                shutil.rmtree(path)
                yield f"Removido: {path}"
            except Exception as e:
                yield f"⚠️ ERRO ao remover {path}: {e}"
    yield from executar_comando_cmd("gpupdate /force", timeout=120)
    yield "Restauração das GPOs padrão concluída."

def resetar_microsoft_store():
    """Limpa o cache e re-registra a Microsoft Store."""
    yield "Iniciando reset da Microsoft Store..."
    yield from executar_comando_cmd("wsreset.exe -q", timeout=120)
    yield "Comando de limpeza de cache enviado."
    yield "Re-registrando o aplicativo da Store..."
    comando = 'Get-AppxPackage *WindowsStore* -AllUsers | ForEach-Object {Add-AppxPackage -DisableDevelopmentMode -Register "$($_.InstallLocation)\\AppXManifest.xml"}'
    yield from executar_comando_powershell(comando)
    yield "Comando de re-registro enviado."

def ajustar_melhor_desempenho():
    """Habilitar a opção Ajustar para obter o melhor desempenho, desativar serviços e aplicar configurações nos usuários padrão."""
    ps, cmd = executar_comando_powershell, executar_comando_cmd

    yield "Iniciando ajuste para melhor desempenho..."

    # Aplicar em todos os usuários padrão
    usuarios = ["UFG", "Aluno", "Usuário"]
    for usuario in usuarios:
        user_dir = fr"C:\Users\{usuario}"
        ntuser_path = os.path.join(user_dir, "NTUSER.DAT")

        if not os.path.exists(user_dir):
            yield f"⚠️ Usuário {usuario} não encontrado, pulando..."
            continue

        yield f"Aplicando configurações para o usuário {usuario}..."
        yield from ps(fr'reg load HKU\TempHive "{ntuser_path}"')

        # Ajuste de desempenho e opções visuais
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects VisualFXSetting 2')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced TaskbarAnimations 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\"Control Panel\Desktop" MinAnimate 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize EnableTransparency 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager SubscribedContent-310093Enabled 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager SoftLandingEnabled 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced Start_TrackProgs 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced Start_TrackDocs 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced Start_TrackEnabled 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced Start_ShowRecentDocs 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced Start_NotifyNewApps 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced Start_ShowFrequentPrograms 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced Start_ShowRecommendations 0')

        yield "Desativando recomendações e ofertas..."
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager SubscribedContent-338389Enabled 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager SubscribedContent-353694Enabled 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager SubscribedContent-353696Enabled 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager SubscribedContent-353698Enabled 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager SubscribedContent-353699Enabled 0')
        yield from ps(r'Set-ItemProperty HKU:\TempHive\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager SubscribedContent-353700Enabled 0')

        yield from ps(r'reg unload HKU\TempHive')
        yield f"Configurações aplicadas para o usuário {usuario}."

    yield "Ajustando prioridade de I/O do sistema..."
    yield from ps(r'Set-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Control\PriorityControl Win32PrioritySeparation 24')

    yield "Aumentando tamanho do cache de disco..."
    yield from ps(r'Set-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters MaxRawWorkItems 512')

    yield "Desativando serviços do Xbox..."
    for s in ["XboxGipSvc", "XboxNetApiSvc", "XblAuthManager", "XblGameSave"]:
        yield from ps(f'Stop-Service {s} -Force; Set-Service {s} -StartupType Disabled')
    yield "Serviços do Xbox desativados com sucesso."

    yield "Desativando serviços adicionais..."
    for s in ["WpcSvc", "WpcMonSvc", "DiagTrack", "dmwappushservice", "DusmSvc", "GameInputSvc", "ScPolicySvc", "WbioSrvc", "BDESVC", "SCardSvr", "icssvc", "WerSvc", "SensorService", "PhoneSvc", "SysMain"]:
        yield from ps(f'Stop-Service {s} -Force; Set-Service {s} -StartupType Disabled')
    yield "Todos os serviços adicionais foram desativados com sucesso."

    yield "Desativando aplicativos em segundo plano..."
    apps_pfn = [
        "Microsoft.WindowsTips_8wekyb3d8bbwe",              # Dicas
        "microsoft.windowscommunicationsapps_8wekyb3d8bbwe",# Email e calendário
        "Microsoft.ZuneVideo_8wekyb3d8bbwe",                # Filmes e TV
        "Microsoft.Copilot_8wekyb3d8bbwe",                  # Copilot
        "Microsoft.GetHelp_8wekyb3d8bbwe",                  # Obter ajuda
        "Microsoft.Office.OneNote_8wekyb3d8bbwe",           # OneNote
        "Microsoft.MSPaint_8wekyb3d8bbwe",                  # Paint 3D
        "Microsoft.Print3D_8wekyb3d8bbwe",                  # Print 3D
        "Microsoft.Sway_8wekyb3d8bbwe",                     # Sway
        "Microsoft.YourPhone_8wekyb3d8bbwe",                # Vincular ao Celular
        "Microsoft.Microsoft3DViewer_8wekyb3d8bbwe"         # Visualizador 3D
    ]
    for app in apps_pfn:
        yield from ps(fr'Set-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications\{app} Disabled 1')

    yield "Desabilitando inicialização automática de aplicativos..."
    startup_apps = [
        "MicrosoftEdgeUpdate",   # Edge
        "OneDrive",              # OneDrive
        "Copilot",               # Microsoft 365 Copilot
        "YourPhone"              # Vincular ao Celular
    ]
    for app in startup_apps:
        yield from ps(fr'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v {app} /t REG_SZ /d "" /f')

    yield "Ocultando ícone Reunir Agora..."
    yield from ps(r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer" /v HideSCAMeetNow /t REG_DWORD /d 1 /f')

    yield "Desligando notícias e interesses..."
    yield from ps(r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Feeds" /v ShellFeedsTaskbarViewMode /t REG_DWORD /d 2 /f')

    yield "Desativando notificações e ações"
    yield from ps(r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\UserProfileEngagement" /v ScoobeSystemSettingEnabled /t REG_DWORD /d 0 /f')
    yield from ps(r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\UserProfileEngagement" /v EnableScoobeExperience /t REG_DWORD /d 0 /f')
    yield from ps(r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager" /v SubscribedContent-338388Enabled /t REG_DWORD /d 0 /f')

    yield "Desativando controle por voz e reconhecimento de fala online..."
    yield from ps(r'reg add "HKCU\Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy" /v HasAccepted /t REG_DWORD /d 0 /f')
    yield from ps(r'reg add "HKCU\Software\Microsoft\Speech_OneCore\Settings\VoiceActivation" /v VoiceActivationEnable /t REG_DWORD /d 0 /f')

    yield "Desativando histórico de atividades..."
    yield from ps(r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\ActivityHistory" /v EnableActivityFeed /t REG_DWORD /d 0 /f')
    yield from ps(r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\ActivityHistory" /v PublishUserActivities /t REG_DWORD /d 0 /f')
    yield from ps(r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\ActivityHistory" /v UploadUserActivities /t REG_DWORD /d 0 /f')

    yield "Desativando exibição dos ultimos arquivos e fotos ..."
    yield from ps(r' Remove-Item "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\HomeFolderDesktop\NameSpace\DelegateFolders\{3134ef9c-6b18-4996-ad04-ed5912e00eb5}" -Recurse')
    yield from ps(r' Remove-Item "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\HomeFolderDesktop\NameSpace\DelegateFolders\{3936E9E4-D92C-4EEE-A85A-BC16D5EA0819}" -Recurse')

    yield "Desativando Cortana..."
    yield from ps(r"""
    $Cortana1 = "HKCU:\SOFTWARE\Microsoft\Personalization\Settings"
    $Cortana2 = "HKCU:\SOFTWARE\Microsoft\InputPersonalization"
    $Cortana3 = "HKCU:\SOFTWARE\Microsoft\InputPersonalization\TrainedDataStore"
	If (!(Test-Path $Cortana1)) {
		New-Item $Cortana1
	}
	Set-ItemProperty $Cortana1 AcceptedPrivacyPolicy -Value 0 
	If (!(Test-Path $Cortana2)) {
		New-Item $Cortana2
	}
	Set-ItemProperty $Cortana2 RestrictImplicitTextCollection -Value 1 
	Set-ItemProperty $Cortana2 RestrictImplicitInkCollection -Value 1 
	If (!(Test-Path $Cortana3)) {
		New-Item $Cortana3
	}
	Set-ItemProperty $Cortana3 HarvestContacts -Value 0""")

        #Disables scheduled tasks that are considered unnecessary 
    
    yield "Desativiando serviços desnecessários do Agendador de Tarefas"
    tasks = ["XblGameSaveTaskLogon", "XblGameSaveTask", "Consolidator", "UsbCeip", "DmClient", "DmClientOnScenarioDownload"]
    for task in tasks:
        yield from ps(f'Get-ScheduledTask  {task} | Disable-ScheduledTask')

    yield "Desativa Web Search do Menu Iniciar"
    yield from ps('Set-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Windows Search" DisableWebSearch -Value 1')

    yield "Abrindo o Windows Update..."
    yield from cmd("start ms-settings:windowsupdate", timeout=60)
    yield "✅ Ajuste completo concluído!"

def forcar_atualizacao_gpos():
    """Força a atualização das Políticas de Grupo (gpupdate)."""
    yield "Forçando atualização das Políticas de Grupo (GPOs)..."
    yield from executar_comando_cmd("gpupdate /force", timeout=180)
    yield "Tentativa de atualização de GPO concluída."
          
def remover_aplicativos_indesejados():
    yield "🗑️ Iniciando remoção de aplicativos indesejados"

    apps_para_remover = {
        "Xbox": [
            "Microsoft.XboxApp", "Microsoft.GamingApp", "Microsoft.Xbox.TCUI",
            "Microsoft.XboxGamingOverlay", "Microsoft.XboxGameOverlay",
            "Microsoft.XboxIdentityProvider", "Microsoft.XboxSpeechToTextOverlay",
        ],
        "LinkedIn": ["*LinkedIn*"],
        "Messenger": ["*Messenger*"],
        "Facebook": ["*Facebook*"],
        "Instagram": ["*Instagram*"],
        "TikTok": ["*TikTok*"],
        "Bing Finance": ["*BingFinance*"],
        "Bing News": ["*BingNews*"],
        "Twitter": ["*Twitter*"],
        "Bing Sports": ["*BingSports*"],
        "Bing Weather": ["*BingWeather*"],
        "Bing FoodAndDrink": ["*BingFoodAndDrink*"],
        "Bing Travel": ["*BingTravel*"],
        "Mixed Reality": ["*MixedReality*"],
        "3D Builder": ["*3DBuilder*"],
        "Copilot": ["*Copilot*"],
        "Cortana": ["Microsoft.549981C3F5F10"],
        "Sticky Notes": ["*StickyNotes*"],
        "Skype": ["*SkypeApp*"],
        "Feedback Hub": ["*FeedbackHub*"],
        "Feedback Hub 2": ["*Microsoft.WindowsFeedbackHub*"],
        "Maps": ["*WindowsMaps*"],
        "Solitaire": ["*SolitaireCollection*"],
        "Solitaire 2": ["*Microsoft.MicrosoftSolitaireCollection*"],
        "Outlook": ["*Outlook*"],
        "GetHelp":["*Microsoft.GetHelp*"],
        "Get Started":["*Microsoft.Getstarted*"],
        "Messaging":["*Microsoft.Messaging*"],
        "3D Viewer":["*Microsoft.Microsoft3DViewer*"],
        "Office Hub":["*Microsoft.MicrosoftOfficeHub*"],
        "Speed Test":["*Microsoft.NetworkSpeedTest*"],
        "Sway":["*Microsoft.Office.Sway*"],
        "People":["*Microsoft.People*"],
        "Print 3D":["*Microsoft.Print3D*"],
        "Alarms":["*Microsoft.WindowsAlarms*"],
        "Communications apps":["*microsoft.windowscommunicationsapps*"],
        "Maps":["*Microsoft.WindowsMaps*"],
        "Sound Recorder":["*Microsoft.WindowsSoundRecorder*"],
        "Zune Music ":["*Microsoft.ZuneMusic*"],
        "Zune Video":["*Microsoft.ZuneVideo*"],
        "Candy Crush":["*CandyCrush*"],
        "Spotify":["*Spotify*"]
    }

    yield f"{len(apps_para_remover)} aplicativos/categorias na lista de remoção."

    padroes_unicos = sorted({padrao for padroes in apps_para_remover.values() for padrao in padroes})
    lista_ps = ",".join(f'"{p}"' for p in padroes_unicos)

    script_ps = f"""
    $padroes = @({lista_ps})
    $totalInstalados = 0
    $totalProvisionados = 0

    foreach ($padrao in $padroes) {{
        try {{
            # Buscar pacotes instalados com suporte a curingas
            $pacotesInstalados = Get-AppxPackage -AllUsers | Where-Object {{ $_.Name -like $padrao }}
            foreach ($pacote in $pacotesInstalados) {{
                try {{
                    Remove-AppxPackage -Package $pacote.PackageFullName -AllUsers -ErrorAction Stop
                    $totalInstalados++
                    Write-Output "Removido (instalado, todos os usuarios): $($pacote.Name)"
                }} catch {{
                    Write-Output "AVISO: falha ao remover pacote instalado '$($pacote.Name)': $($_.Exception.Message)"
                }}
            }}
        }} catch {{
            Write-Output "AVISO: falha ao consultar pacotes instalados para '$padrao': $($_.Exception.Message)"
        }}

        try {{
            # Buscar pacotes provisionados com suporte a curingas
            $pacotesProvisionados = Get-AppxProvisionedPackage -Online | Where-Object {{ $_.DisplayName -like $padrao }}
            foreach ($pacote in $pacotesProvisionados) {{
                try {{
                    Remove-AppxProvisionedPackage -Online -PackageName $pacote.PackageName -ErrorAction Stop | Out-Null
                    $totalProvisionados++
                    Write-Output "Removido (provisionado, novos usuarios): $($pacote.DisplayName)"
                }} catch {{
                    Write-Output "AVISO: falha ao remover pacote provisionado '$($pacote.DisplayName)': $($_.Exception.Message)"
                }}
            }}
        }} catch {{
            Write-Output "AVISO: falha ao consultar pacotes provisionados para '$padrao': $($_.Exception.Message)"
        }}
    }}

    Write-Output "RESUMO: $totalInstalados pacote(s) removido(s) dos perfis existentes; $totalProvisionados pacote(s) removido(s) do provisionamento (novos usuarios)."

    # Remoção de jogos Win32 (Steam, Roblox, Epic Games, Battle.net, Riot Client)
    $jogos = @("Steam", "Roblox", "Epic Games Launcher", "Battle.net", "Riot Client")
    foreach ($jogo in $jogos) {{
        try {{
            # Primeiro tenta via Win32_Product
            $programas = Get-WmiObject -Class Win32_Product | Where-Object {{ $_.Name -like "*$jogo*" }}
            foreach ($prog in $programas) {{
                try {{
                    $prog.Uninstall() | Out-Null
                    Write-Output "Removido (Win32 MSI): $($prog.Name)"
                }} catch {{
                    Write-Output "AVISO: falha ao remover jogo '$($prog.Name)': $($_.Exception.Message)"
                }}
            }}

            # Se não encontrado, tenta via Get-Package (mais moderno)
            $pacotes = Get-Package | Where-Object {{ $_.Name -like "*$jogo*" }}
            foreach ($pkg in $pacotes) {{
                try {{
                    $pkg.Provider.UninstallPackage($pkg) | Out-Null
                    Write-Output "Removido (Get-Package): $($pkg.Name)"
                }} catch {{
                    Write-Output "AVISO: falha ao remover pacote '$($pkg.Name)': $($_.Exception.Message)"
                }}
            }}
        }} catch {{
            Write-Output "AVISO: falha ao consultar programas instalados para '$jogo': $($_.Exception.Message)"
        }}
    }}
    """

    yield "Removendo pacotes instalados e provisionados, além de jogos Win32 (Steam, Roblox, Epic Games, Battle.net, Riot Client)..."
    try:
        yield from executar_comando_powershell(script_ps, timeout=900)
    except Exception as e:
        yield f"⚠️ ERRO CRÍTICO ao remover aplicativos/jogos indesejados: {e}"
        return

    yield "✅ Remoção de aplicativos e jogos indesejados concluída."

def manutencao_preventiva_1_click(config):

    inicio = datetime.datetime.now()

    yield f"--- INICIANDO MANUTENÇÃO PREVENTIVA COMPLETA ---\n⏰ Início: {inicio.strftime('%d/%m/%Y %H:%M:%S')}"
    yield "\nPASSO 1/10: Baixando recursos da FCT..."
    yield from baixar_recursos_necessarios(config['URL_REPOSITORIO_FCT'])
    yield "\nPASSO 2/10: Restaurando GPOs Padrão..."
    yield from restaurar_gpos_padrao()
    yield "\nPASSO 3/10: Forçando Atualização de GPOs..."
    yield from forcar_atualizacao_gpos()
    yield "\nPASSO 4/10: Limpeza Geral do Sistema..."
    yield from iniciar_limpeza_sistema(config['URL_BLEACHBIT'])
    yield "\nPASSO 5/10: Aplicando Tema Visual da FCT..."
    yield from aplicar_tema_fct(config['CAMINHO_TEMA'])
    yield "\nPASSO 6/10: Aplicando GPOs da FCT..."
    yield from aplicar_gpos_fct(config['CAMINHO_BASE_GPO'])
    yield "\nPASSO 7/10: Forçando atualização de GPO novamente..."
    yield from instalar_antivirus_apex()
    yield "\nPASSO 8/10: Verificando antivirus..."
    yield from forcar_atualizacao_gpos()
    yield "\nPASSO 9/10: Resetando a Microsoft Store..."
    yield from resetar_microsoft_store()
    yield "\nPASSO 10/10: Habilitando ajuste de desempenho..."
    yield from ajustar_melhor_desempenho()

    fim = datetime.datetime.now()
    tempo_decorrido = fim - inicio

    yield f"\n--- MANUTENÇÃO PREVENTIVA CONCLUÍDA ---"
    yield f"⏰ Fim: {fim.strftime('%d/%m/%Y %H:%M:%S')}"
    yield f"⏱️ Tempo total decorrido: {str(tempo_decorrido).split('.')[0]}"
    yield  "🔄 É recomendado reiniciar o computador para que todas as alterações tenham efeito."
