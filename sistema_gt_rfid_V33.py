#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema Completo de Controle de Acesso GBMX e Checklist de Segurança - Liberar GT
Otimizado para Tela Raspberry Pi de 5 Polegadas (800x480)
Versão 33 - Interface Visual Aprimorada para Touchscreen
Com Diagnóstico de Rede Assíncrono e Interface Não-Bloqueante
"""

import sys
import os
import socket
import threading
import time
import subprocess
import pandas as pd
from datetime import datetime, timedelta

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from PyQt5 import QtWidgets
from PyQt5.QtGui import QFont
from PyQt5.QtCore import pyqtSignal, pyqtSlot, QObject, Qt, QTimer

# ============================================================================
# CONFIGURAÇÕES E GPIO
# ============================================================================
UID_MESTRE = "786538887"

PASTA_CHECKLISTS = os.path.abspath("./checklists")
TEMPO_LIBERACAO_SEGUNDOS = 180

# Inicialização de Hardware GPIO
try:
    import RPi.GPIO as GPIO

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(23, GPIO.OUT, initial=GPIO.LOW)  # LED Verde
    GPIO.setup(24, GPIO.OUT, initial=GPIO.LOW)  # Relé Liberar GT
    HAS_GPIO = True
except Exception as e:
    print(f"[AVISO] RPi.GPIO não inicializado: {e}")
    HAS_GPIO = False


def set_gpios(estado: int):
    """Ajusta o estado lógico das saídas GPIO 23 e GPIO 24"""
    if HAS_GPIO:
        try:
            val = GPIO.HIGH if estado == 1 else GPIO.LOW
            GPIO.output(23, val)
            GPIO.output(24, val)
            print(f"[GPIO] Saídas 23 e 24 alteradas para: {estado}")
        except Exception as e:
            print(f"[GPIO] Erro ao acionar GPIOs: {e}")


def testar_conexao_internet(host="8.8.8.8", port=53, timeout=3):
    """Verifica se há conexão ativa com a internet utilizando timeout curto"""
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def obter_wifi_ssid():
    """Obtém o SSID do Wi-Fi atualmente conectado no Raspberry Pi OS."""
    try:
        # Método 1: via iwgetid
        result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True, timeout=2)
        ssid = result.stdout.strip()
        if ssid:
            return ssid

        # Método 2: via nmcli
        result = subprocess.run(['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'], capture_output=True, text=True, timeout=2)
        for line in result.stdout.splitlines():
            if line.startswith('yes:'):
                return line.split('yes:')[1]
    except Exception:
        pass
    return None


def conectar_wifi_nmcli(ssid, senha):
    """Tenta conectar à rede Wi-Fi/Hotspot via nmcli no Linux/Raspberry Pi"""
    try:
        subprocess.run(["nmcli", "radio", "wifi", "on"], capture_output=True, timeout=5)
        cmd = ["nmcli", "dev", "wifi", "connect", ssid, "password", senha]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if res.returncode == 0 or "successfully activated" in res.stdout.lower():
            return True, "Conectado com sucesso!"
        else:
            msg_erro = res.stderr.strip() if res.stderr.strip() else res.stdout.strip()
            return False, f"Falha na conexão: {msg_erro[:60]}"
    except subprocess.TimeoutExpired:
        return False, "Tempo limite esgotado ao conectar ao Wi-Fi."
    except Exception as e:
        return False, f"Erro ao conectar: {str(e)[:60]}"


# ============================================================================
# TECLADO VIRTUAL TOUCH (OTIMIZADO PARA TOUCHSCREEN 800x480)
# ============================================================================
class TecladoVirtual(QtWidgets.QWidget):
    tecla_pressionada = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.maiusculo = True
        self.configurar_layout()

    def configurar_layout(self):
        self.layout_principal = QtWidgets.QVBoxLayout(self)
        self.layout_principal.setContentsMargins(2, 2, 2, 2)
        self.layout_principal.setSpacing(4)

        self.linhas_teclas = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '⌫'],
            ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
            ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', '-'],
            ['z', 'x', 'c', 'v', 'b', 'n', 'm', '.', '_', '@'],
            ['a/A', 'ESPAÇO', 'LIMPAR']
        ]

        self.botoes = []
        self.renderizar_teclado()

    def renderizar_teclado(self):
        while self.layout_principal.count():
            item = self.layout_principal.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        self.botoes.clear()

        style_tecla = """
            QPushButton {
                background-color: #E0E0E0;
                color: #111111;
                font-weight: bold;
                font-size: 14px;
                border: 1px solid #BDBDBD;
                border-radius: 6px;
            }
            QPushButton:pressed {
                background-color: #1565C0;
                color: #FFFFFF;
            }
        """

        style_especial = """
            QPushButton {
                background-color: #CFD8DC;
                color: #111111;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #90A4AE;
                border-radius: 6px;
            }
            QPushButton:pressed {
                background-color: #1565C0;
                color: #FFFFFF;
            }
        """

        for linha in self.linhas_teclas:
            h_layout = QtWidgets.QHBoxLayout()
            h_layout.setSpacing(4)
            for k in linha:
                btn_txt = k
                if len(k) == 1 and k.isalpha():
                    btn_txt = k.upper() if self.maiusculo else k.lower()

                btn = QtWidgets.QPushButton(btn_txt)
                btn.setFixedHeight(38)

                if k in ['⌫', 'LIMPAR', 'a/A']:
                    btn.setStyleSheet(style_especial)
                elif k == 'ESPAÇO':
                    btn.setStyleSheet(style_tecla)
                    btn.setMinimumWidth(200)
                else:
                    btn.setStyleSheet(style_tecla)

                btn.clicked.connect(lambda checked, val=k: self.tratar_clique(val))
                h_layout.addWidget(btn)
                self.botoes.append(btn)

            self.layout_principal.addLayout(h_layout)

    def tratar_clique(self, tecla):
        if tecla == 'a/A':
            self.maiusculo = not self.maiusculo
            self.renderizar_teclado()
        elif tecla == '⌫':
            self.tecla_pressionada.emit("BACKSPACE")
        elif tecla == 'LIMPAR':
            self.tecla_pressionada.emit("CLEAR")
        elif tecla == 'ESPAÇO':
            self.tecla_pressionada.emit(" ")
        else:
            val = tecla.upper() if (len(tecla) == 1 and tecla.isalpha() and self.maiusculo) else tecla
            self.tecla_pressionada.emit(val)


# ============================================================================
# EMISSOR DE SINAIS E THREAD RFID ROBUSTA (RC522)
# ============================================================================
class RFIDSignals(QObject):
    uid_recebido = pyqtSignal(str)


class LeituraRC522(threading.Thread):
    def __init__(self):
        super().__init__()
        self.signals = RFIDSignals()
        self.ativo = True
        self.daemon = True

    @staticmethod
    def converter_uid_rc522(id_card):
        try:
            valor = int(id_card)
            if valor <= 0:
                return ""

            if valor > 0xFFFFFFFF:
                num_bytes = (valor.bit_length() + 7) // 8
                uid_bytes = valor.to_bytes(num_bytes, byteorder="big")
                return str(int.from_bytes(uid_bytes[:4], byteorder="little"))

            return str(valor)
        except (TypeError, ValueError, OverflowError):
            return str(id_card).strip()

    def run(self):
        reader = None
        erros_consecutivos = 0

        while self.ativo:
            try:
                if reader is None:
                    from mfrc522 import SimpleMFRC522
                    reader = SimpleMFRC522()
                    print("✓ Leitor RC522 inicializado/reiniciado com sucesso!")

                id_card, _ = reader.read_no_block()

                if id_card:
                    uid = self.converter_uid_rc522(id_card)
                    print(f"[RFID] UID bruto: {id_card} | UID normalizado: {uid}")
                    self.signals.uid_recebido.emit(uid)
                    erros_consecutivos = 0
                    time.sleep(0.8)
                else:
                    time.sleep(0.1)

            except Exception as e:
                erros_consecutivos += 1
                if erros_consecutivos >= 3:
                    print(f"[RFID] Falha de comunicação no SPI ({e}). Reiniciando leitor...")
                    reader = None
                    erros_consecutivos = 0
                time.sleep(0.2)

    def parar(self):
        self.ativo = False


# ============================================================================
# GERENCIAMENTO DE DADOS (EXCEL ROBUSTO COM LEITURA STRING)
# ============================================================================
class GerenciadorDados:
    def __init__(self, arquivo_excel='Lista_Basedecrachás.xlsx'):
        self.arquivo = arquivo_excel
        self.df = None
        self.carregar_planilha()

    def carregar_planilha(self):
        try:
            if os.path.exists(self.arquivo):
                self.df = pd.read_excel(self.arquivo, dtype=str)

                mapeamento = {}
                for col in self.df.columns:
                    col_norm = str(col).strip().upper()
                    if col_norm in ['CRACHA', 'CRACHÁ', 'CARD', 'UID']:
                        mapeamento[col] = 'CRACHÁ'
                    elif col_norm in ['NOME', 'OPERADOR', 'FUNCIONARIO']:
                        mapeamento[col] = 'NOME'
                    elif col_norm in ['MATRICULA', 'MATRÍCULA', 'ID']:
                        mapeamento[col] = 'MATRICULA'
                    elif col_norm in ['STATUS', 'SITUACAO', 'SITUAÇÃO']:
                        mapeamento[col] = 'STATUS'

                self.df.rename(columns=mapeamento, inplace=True)

                if 'STATUS' not in self.df.columns:
                    self.df['STATUS'] = 'D'
                    self.salvar_planilha()

                print(f"✓ Base de dados carregada ({len(self.df)} registros)")
                return True
            else:
                print(f"✗ Arquivo '{self.arquivo}' não foi encontrado no diretório!")
                return False
        except Exception as e:
            print(f"✗ Erro ao carregar planilha: {e}")
            return False

    def salvar_planilha(self):
        try:
            if self.df is not None:
                self.df.to_excel(self.arquivo, index=False)
                return True
        except Exception as e:
            print(f"[ERRO SALVAR] {e}")
            return False

    def _normalizar_val(self, valor):
        if pd.isnull(valor):
            return ""
        v_str = str(valor).strip()
        if v_str.endswith('.0'):
            v_str = v_str[:-2]
        try:
            return str(int(v_str))
        except ValueError:
            return v_str.upper()

    def buscar_por_cracha(self, uid):
        if self.df is None or 'CRACHÁ' not in self.df.columns:
            print("[BUSCA] Planilha não carregada ou coluna 'CRACHÁ' inexistente.")
            return None
        try:
            uid_alvo = self._normalizar_val(uid)
            print(f"[BUSCA PLANILHA] Comparando UID recebido '{uid}' (norm: '{uid_alvo}')")

            for _, linha in self.df.iterrows():
                cracha_planilha = self._normalizar_val(linha['CRACHÁ'])
                if cracha_planilha == uid_alvo:
                    nome = str(linha.get('NOME', 'Desconhecido')).strip()
                    matricula = self._normalizar_val(linha.get('MATRICULA', '0'))
                    status = str(linha.get('STATUS', 'D')).strip().upper()
                    print(f"✓ [ENCONTRADO] Usuário: {nome} | Status: {status}")
                    return {
                        'nome': nome,
                        'matricula': matricula,
                        'cracha': cracha_planilha,
                        'status': status
                    }

            print(f"✗ [NÃO ENCONTRADO] Nenhum registro compatível com UID '{uid_alvo}'")
            return None
        except Exception as e:
            print(f"[ERRO BUSCA] {e}")
            return None

    def alterar_status(self, uid, novo_status):
        if self.df is None or 'CRACHÁ' not in self.df.columns:
            return False
        try:
            uid_alvo = self._normalizar_val(uid)
            for idx, linha in self.df.iterrows():
                if self._normalizar_val(linha['CRACHÁ']) == uid_alvo:
                    self.df.at[idx, 'STATUS'] = novo_status
                    return self.salvar_planilha()
            return False
        except Exception as e:
            print(f"[ERRO ALTERAR STATUS] {e}")
            return False


# ============================================================================
# JANELA PRINCIPAL DO SISTEMA GT
# ============================================================================
class SistemaGT(QtWidgets.QMainWindow):
    sinal_git_finalizado = pyqtSignal(bool, str)
    sinal_wifi_finalizado = pyqtSignal(bool, str)
    sinal_diagnostico_rede = pyqtSignal(bool, bool, str)  # (tem_wifi, tem_internet, ssid)

    def __init__(self):
        super().__init__()

        self.dados = GerenciadorDados()

        self.labels_data_hora = []
        self.checklists_aprovados_turno = {}

        self.operador_atual = None
        self.respostas_checklist = {}
        self.finalizacao_em_andamento = False
        self.thread_finalizacao = None

        self.ultimo_uid_lido = None
        self.tempo_ultimo_lido = 0
        self.uid_bloqueado_ate_novo_cracha = None

        # Conectar sinais
        self.sinal_git_finalizado.connect(self.ao_concluir_sincronizacao_git)
        self.sinal_wifi_finalizado.connect(self.ao_concluir_conexao_wifi)
        self.sinal_diagnostico_rede.connect(self.ao_concluir_diagnostico_rede)

        self.leitor_rfid = LeituraRC522()
        self.leitor_rfid.signals.uid_recebido.connect(
            self.processar_rfid,
            type=Qt.QueuedConnection
        )
        self.leitor_rfid.start()

        self.timer_liberacao = QTimer(self)
        self.timer_liberacao.setSingleShot(True)
        self.timer_liberacao.timeout.connect(self.finalizar_tempo_liberacao)
        self.fim_liberacao = None

        self.timer_cronometro = QTimer(self)
        self.timer_cronometro.setInterval(1000)
        self.timer_cronometro.timeout.connect(self.atualizar_cronometro_liberacao)

        self.timer_relogio = QTimer(self)
        self.timer_relogio.timeout.connect(self.atualizar_relogio)
        self.timer_relogio.start(1000)

        self.perguntas = [
            "O leitor de crachá encontra-se em pleno funcionamento?",
            "Os botões de acionamento, emergência e os controles do painel encontram-se em perfeito funcionamento?",
            "A sirene e random do equipamento encontra-se em pleno funcionamento?",
            "O equipamento encontra-se em condições seguras de uso, sem apresentar danos, ruído anormal, trincas, modificações não autorizadas, peças faltantes ou instaladas de forma inadequada?",
            "A fixação do equipamento ao solo está adequada, sem a presença de parafusos soltos?",
            "A corda para tracionamento do equipamento encontra-se em boas condições de uso?",
            "A corrente e os acessórios de amarração da carga encontram-se em boas condições de uso?",
            "A carga a ser tracionada está dentro dos limites operacionais do equipamento?",
            "Existe demarcação no solo que assegure o posicionamento seguro do operador?",
            "Você possui o treinamento obrigatório para a operação do guincho tracionador?",
            "Após a verificação dos itens acima, a operação do guincho tracionador pode ser realizada com segurança?"
        ]

        self.campo_focado_wifi = None
        self.configurar_interface()
        self.atualizar_relogio()

    def obter_texto_turno_atual(self):
        hora = datetime.now().hour
        if 6 <= hora < 14:
            return "TURNO 1"
        elif 14 <= hora < 22:
            return "TURNO 2"
        else:
            return "TURNO 3"

    def obter_turno_atual(self):
        agora = datetime.now()
        hora = agora.hour
        data_str = agora.strftime("%Y-%m-%d")

        if 6 <= hora < 14:
            return f"{data_str}_T1"
        elif 14 <= hora < 22:
            return f"{data_str}_T2"
        else:
            if hora < 6:
                data_str = (agora - timedelta(days=1)).strftime("%Y-%m-%d")
            return f"{data_str}_T3"

    def invalidar_checklists_do_turno(self):
        turno_atual = self.obter_turno_atual()
        self.checklists_aprovados_turno[turno_atual] = set()

    def criar_widget_cabecalho(self):
        lbl = QtWidgets.QLabel()
        lbl.setFont(QFont("Arial", 13, QFont.Bold))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #1A237E; background-color: #E8EAF6; padding: 6px 14px; border-radius: 8px;")
        self.labels_data_hora.append(lbl)
        return lbl

    def atualizar_relogio(self):
        texto = f"{datetime.now().strftime('%d/%m/%Y - %H:%M:%S')}  |  {self.obter_texto_turno_atual()}"
        for lbl in self.labels_data_hora:
            lbl.setText(texto)

    def atualizar_cronometro_liberacao(self):
        if self.fim_liberacao is None:
            return

        restante = self.fim_liberacao - time.monotonic()
        if restante <= 0:
            if hasattr(self, 'lbl_tempo_restante'):
                self.lbl_tempo_restante.setText("00:00:00")
            self.finalizar_tempo_liberacao()
            return

        segundos = int(restante + 0.999999)
        horas, resto = divmod(segundos, 3600)
        minutos, segundos = divmod(resto, 60)
        if hasattr(self, 'lbl_tempo_restante'):
            self.lbl_tempo_restante.setText(f"{horas:02d}:{minutos:02d}:{segundos:02d}")

    def configurar_interface(self):
        self.setWindowTitle("SISTEMA GBMX - LIBERAR GT")
        self.setStyleSheet("background-color: #f4f4f9;")

        self.setFixedSize(800, 480)
        self.showFullScreen()

        self.central_widget = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.central_widget)

        self.tela_liberar_gt = self.criar_tela_menu_liberar_gt()
        self.tela_leitura = self.criar_tela_leitura()
        self.tela_wifi = self.criar_tela_wifi()
        self.tela_status_rede = self.criar_tela_status_rede()

        self.telas_checklist_perguntas = [
            self.criar_tela_par_perguntas(0, 1),
            self.criar_tela_par_perguntas(2, 3),
            self.criar_tela_par_perguntas(4, 5),
            self.criar_tela_par_perguntas(6, 7),
            self.criar_tela_par_perguntas(8, 9),
            self.criar_tela_pergunta_final(10)
        ]

        self.tela_aprovado = self.criar_tela_aprovado()
        self.tela_reprovado_bloqueado = self.criar_tela_reprovado_bloqueado()
        self.tela_confirmacao_operacao = self.criar_tela_confirmacao_operacao()
        self.tela_processando_checklist = self.criar_tela_processando_checklist()

        self.central_widget.addWidget(self.tela_liberar_gt)
        self.central_widget.addWidget(self.tela_leitura)
        self.central_widget.addWidget(self.tela_wifi)
        self.central_widget.addWidget(self.tela_status_rede)
        for t in self.telas_checklist_perguntas:
            self.central_widget.addWidget(t)
        self.central_widget.addWidget(self.tela_aprovado)
        self.central_widget.addWidget(self.tela_reprovado_bloqueado)
        self.central_widget.addWidget(self.tela_confirmacao_operacao)
        self.central_widget.addWidget(self.tela_processando_checklist)

        self.central_widget.setCurrentWidget(self.tela_liberar_gt)
        self.estado_atual = "MENU_GT"

    def mudar_tela(self, tela, novo_estado):
        self.estado_atual = novo_estado
        self.ultimo_uid_lido = None
        self.uid_bloqueado_ate_novo_cracha = None
        self.central_widget.setCurrentWidget(tela)

    # ========================================================================
    # TELA INICIAL
    # ========================================================================
    def criar_tela_menu_liberar_gt(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)

        lbl_hdr = self.criar_widget_cabecalho()

        titulo = QtWidgets.QLabel("MENU - LIBERAR GT")
        titulo.setFont(QFont("Arial", 18, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("color: #212121; margin-top: 2px; margin-bottom: 4px;")

        btn_style_base = """
            QPushButton {{
                background-color: {cor};
                color: white;
                border-radius: 8px;
                font-weight: bold;
                font-size: 14pt;
            }}
            QPushButton:pressed {{
                background-color: {cor_press};
            }}
        """

        btn_liberar = QtWidgets.QPushButton("1 - LIBERAR EQUIPAMENTO")
        btn_liberar.setFixedSize(540, 52)
        btn_liberar.setStyleSheet(btn_style_base.format(cor="#2E7D32", cor_press="#1B5E20"))
        btn_liberar.clicked.connect(
            lambda: self.preparar_leitura("LIBERAR_EQUIPAMENTO", "Aproxime o crachá para LIBERAR O EQUIPAMENTO"))

        btn_habilitar = QtWidgets.QPushButton("2 - HABILITAR USUÁRIO")
        btn_habilitar.setFixedSize(540, 52)
        btn_habilitar.setStyleSheet(btn_style_base.format(cor="#1565C0", cor_press="#0D47A1"))
        btn_habilitar.clicked.connect(
            lambda: self.preparar_leitura("HABILITAR_USUARIO_MESTRE", "Aproxime o CRACHÁ MESTRE para autorizar"))

        btn_desabilitar = QtWidgets.QPushButton("3 - DESABILITAR USUÁRIO")
        btn_desabilitar.setFixedSize(540, 52)
        btn_desabilitar.setStyleSheet(btn_style_base.format(cor="#C62828", cor_press="#8E0000"))
        btn_desabilitar.clicked.connect(
            lambda: self.preparar_leitura("DESABILITAR_USUARIO_MESTRE", "Aproxime o CRACHÁ MESTRE para autorizar"))

        btn_git = QtWidgets.QPushButton("4 - SINCRONIZAR CHECKLISTS (GIT)")
        btn_git.setFixedSize(540, 52)
        btn_git.setStyleSheet(btn_style_base.format(cor="#E65100", cor_press="#BF360C"))
        btn_git.clicked.connect(self.ao_clicar_opcao_git)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(titulo, alignment=Qt.AlignCenter)
        layout.addWidget(btn_liberar, alignment=Qt.AlignCenter)
        layout.addWidget(btn_habilitar, alignment=Qt.AlignCenter)
        layout.addWidget(btn_desabilitar, alignment=Qt.AlignCenter)
        layout.addWidget(btn_git, alignment=Qt.AlignCenter)

        tela.setLayout(layout)
        return tela

    # ========================================================================
    # TELA E FLUXO DA OPÇÃO 4: DIAGNÓSTICO DE REDE E SINCRONIZAR GIT
    # ========================================================================
    def criar_tela_status_rede(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tela)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(12)

        lbl_hdr = self.criar_widget_cabecalho()

        titulo = QtWidgets.QLabel("DIAGNÓSTICO DE REDE E INTERNET")
        titulo.setFont(QFont("Arial", 16, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("color: #1A237E;")

        self.lbl_status_rede_detalhe = QtWidgets.QLabel("Verificando conexão com a internet...")
        self.lbl_status_rede_detalhe.setFont(QFont("Arial", 13, QFont.Bold))
        self.lbl_status_rede_detalhe.setAlignment(Qt.AlignCenter)
        self.lbl_status_rede_detalhe.setWordWrap(True)
        self.lbl_status_rede_detalhe.setStyleSheet(
            "color: #1565C0; padding: 15px; border: 2px solid #1565C0; border-radius: 10px; background-color: #E3F2FD;"
        )
        self.lbl_status_rede_detalhe.setFixedSize(680, 160)

        # Container dos Botões de Ação
        self.container_btn_rede = QtWidgets.QWidget()
        h_btn = QtWidgets.QHBoxLayout(self.container_btn_rede)
        h_btn.setSpacing(12)

        style_btn = """
            QPushButton {{
                background-color: {cor};
                color: white;
                border-radius: 8px;
                font-weight: bold;
                font-size: 12pt;
            }}
            QPushButton:pressed {{
                background-color: {cor_press};
            }}
        """

        self.btn_voltar_rede = QtWidgets.QPushButton("VOLTAR AO MENU")
        self.btn_voltar_rede.setFixedHeight(48)
        self.btn_voltar_rede.setStyleSheet(style_btn.format(cor="#757575", cor_press="#424242"))
        self.btn_voltar_rede.clicked.connect(lambda: self.mudar_tela(self.tela_liberar_gt, "MENU_GT"))

        self.btn_ir_wifi = QtWidgets.QPushButton("CONFIGURAR WI-FI")
        self.btn_ir_wifi.setFixedHeight(48)
        self.btn_ir_wifi.setStyleSheet(style_btn.format(cor="#E65100", cor_press="#BF360C"))
        self.btn_ir_wifi.clicked.connect(lambda: self.mudar_tela(self.tela_wifi, "CONFIGURAR_WIFI"))

        self.btn_tentar_rede = QtWidgets.QPushButton("TENTAR NOVAMENTE")
        self.btn_tentar_rede.setFixedHeight(48)
        self.btn_tentar_rede.setStyleSheet(style_btn.format(cor="#1565C0", cor_press="#0D47A1"))
        self.btn_tentar_rede.clicked.connect(self.ao_clicar_opcao_git)

        h_btn.addWidget(self.btn_voltar_rede)
        h_btn.addWidget(self.btn_ir_wifi)
        h_btn.addWidget(self.btn_tentar_rede)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(titulo, alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl_status_rede_detalhe, alignment=Qt.AlignCenter)
        layout.addWidget(self.container_btn_rede, alignment=Qt.AlignCenter)

        tela.setLayout(layout)
        return tela

    def ao_clicar_opcao_git(self):
        """Inicia a verificação de rede assíncrona sem travar a interface."""
        self.mudar_tela(self.tela_status_rede, "DIAGNOSTICO_REDE")
        self.lbl_status_rede_detalhe.setText("Verificando conexão com a rede e internet...\nAguarde...")
        self.lbl_status_rede_detalhe.setStyleSheet(
            "color: #1565C0; padding: 15px; border: 2px solid #1565C0; border-radius: 10px; background-color: #E3F2FD;"
        )
        self.container_btn_rede.setEnabled(False)

        def _worker_diagnostico():
            ssid = obter_wifi_ssid()
            tem_wifi = bool(ssid)
            tem_internet = testar_conexao_internet(timeout=3) if tem_wifi else False
            self.sinal_diagnostico_rede.emit(tem_wifi, tem_internet, ssid or "")

        threading.Thread(target=_worker_diagnostico, daemon=True).start()

    @pyqtSlot(bool, bool, str)
    def ao_concluir_diagnostico_rede(self, tem_wifi, tem_internet, ssid):
        self.container_btn_rede.setEnabled(True)

        # CASO 1: Não está conectado ao Wi-Fi
        if not tem_wifi:
            self.lbl_wifi_status.setText("Nenhuma rede Wi-Fi conectada.\nInforme os dados da rede/hotspot:")
            self.lbl_wifi_status.setStyleSheet("color: #C62828; font-weight: bold; font-size: 13px;")
            self.mudar_tela(self.tela_wifi, "CONFIGURAR_WIFI")
            return

        # CASO 2: Conectado ao Wi-Fi E tem Internet
        if tem_wifi and tem_internet:
            self.preparar_leitura(
                "SINCRONIZAR_GIT_MESTRE",
                f"Conectado à rede: {ssid}\n\nAproxime o CRACHÁ MESTRE para autorizar a Sincronização"
            )
        else:
            # CASO 3: Conectado ao Wi-Fi, mas SEM Internet
            msg_detalhe = (
                f"REDE WI-FI: {ssid}\n"
                f"STATUS DA CONEXÃO: Conectado ao Roteador/Hotspot\n"
                f"ACESSO À INTERNET: Sem Acesso\n\n"
                f"Verifique se o roteador/hotspot possui conexão com a internet e tente novamente."
            )
            self.lbl_status_rede_detalhe.setText(msg_detalhe)
            self.lbl_status_rede_detalhe.setStyleSheet(
                "color: #C62828; padding: 15px; border: 2px solid #C62828; border-radius: 10px; background-color: #FFEBEE;"
            )

    def criar_tela_wifi(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tela)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(6)

        lbl_hdr = self.criar_widget_cabecalho()

        titulo = QtWidgets.QLabel("CONFIGURAÇÃO DE WI-FI / HOTSPOT")
        titulo.setFont(QFont("Arial", 15, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("color: #1A237E;")

        self.lbl_wifi_status = QtWidgets.QLabel("Informe o SSID e a Senha para conectar:")
        self.lbl_wifi_status.setFont(QFont("Arial", 12))
        self.lbl_wifi_status.setAlignment(Qt.AlignCenter)

        # Campos de texto
        form_layout = QtWidgets.QHBoxLayout()
        form_layout.setSpacing(10)

        lbl_ssid = QtWidgets.QLabel("Rede (SSID):")
        lbl_ssid.setFont(QFont("Arial", 12, QFont.Bold))
        self.input_ssid = QtWidgets.QLineEdit()
        self.input_ssid.setFixedHeight(36)
        self.input_ssid.setFont(QFont("Arial", 12))
        self.input_ssid.setStyleSheet("background-color: white; border: 1px solid #777; border-radius: 6px; padding: 2px 8px;")

        lbl_senha = QtWidgets.QLabel("Senha:")
        lbl_senha.setFont(QFont("Arial", 12, QFont.Bold))
        self.input_senha = QtWidgets.QLineEdit()
        self.input_senha.setEchoMode(QtWidgets.QLineEdit.Password)
        self.input_senha.setFixedHeight(36)
        self.input_senha.setFont(QFont("Arial", 12))
        self.input_senha.setStyleSheet("background-color: white; border: 1px solid #777; border-radius: 6px; padding: 2px 8px;")

        self.input_ssid.mousePressEvent = lambda e: self.definir_foco_campo(self.input_ssid)
        self.input_senha.mousePressEvent = lambda e: self.definir_foco_campo(self.input_senha)

        form_layout.addWidget(lbl_ssid)
        form_layout.addWidget(self.input_ssid, 1)
        form_layout.addWidget(lbl_senha)
        form_layout.addWidget(self.input_senha, 1)

        # Teclado Virtual
        self.teclado = TecladoVirtual()
        self.teclado.tecla_pressionada.connect(self.ao_digitar_teclado)

        # Botoes
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(12)

        btn_style_nav = """
            QPushButton {{
                background-color: {cor};
                color: white;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13pt;
            }}
            QPushButton:pressed {{
                background-color: {cor_press};
            }}
        """

        self.btn_conectar_wifi = QtWidgets.QPushButton("CONECTAR E CONTINUAR")
        self.btn_conectar_wifi.setFixedHeight(44)
        self.btn_conectar_wifi.setStyleSheet(btn_style_nav.format(cor="#2E7D32", cor_press="#1B5E20"))
        self.btn_conectar_wifi.clicked.connect(self.iniciar_conexao_wifi)

        btn_cancelar_wifi = QtWidgets.QPushButton("CANCELAR / VOLTAR")
        btn_cancelar_wifi.setFixedHeight(44)
        btn_cancelar_wifi.setStyleSheet(btn_style_nav.format(cor="#757575", cor_press="#424242"))
        btn_cancelar_wifi.clicked.connect(lambda: self.mudar_tela(self.tela_liberar_gt, "MENU_GT"))

        btn_layout.addWidget(btn_cancelar_wifi)
        btn_layout.addWidget(self.btn_conectar_wifi)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(titulo, alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl_wifi_status, alignment=Qt.AlignCenter)
        layout.addLayout(form_layout)
        layout.addWidget(self.teclado)
        layout.addLayout(btn_layout)

        self.definir_foco_campo(self.input_ssid)

        tela.setLayout(layout)
        return tela

    def definir_foco_campo(self, campo):
        self.campo_focado_wifi = campo
        style_padrao = "background-color: white; border: 1px solid #777; border-radius: 6px; padding: 2px 8px; font-size: 12pt;"
        style_foco = "background-color: #FFF9C4; border: 2px solid #1565C0; border-radius: 6px; padding: 2px 8px; font-size: 12pt;"
        self.input_ssid.setStyleSheet(style_padrao)
        self.input_senha.setStyleSheet(style_padrao)
        campo.setStyleSheet(style_foco)

    def ao_digitar_teclado(self, valor):
        if not self.campo_focado_wifi:
            return

        if valor == "BACKSPACE":
            self.campo_focado_wifi.setText(self.campo_focado_wifi.text()[:-1])
        elif valor == "CLEAR":
            self.campo_focado_wifi.clear()
        else:
            self.campo_focado_wifi.setText(self.campo_focado_wifi.text() + valor)

    def iniciar_conexao_wifi(self):
        ssid = self.input_ssid.text().strip()
        senha = self.input_senha.text().strip()

        if not ssid:
            self.lbl_wifi_status.setText("Por favor, digite o nome da rede (SSID).")
            self.lbl_wifi_status.setStyleSheet("color: #C62828; font-weight: bold;")
            return

        self.lbl_wifi_status.setText(f"Conectando à rede '{ssid}'... Aguarde...")
        self.lbl_wifi_status.setStyleSheet("color: #1565C0; font-weight: bold;")
        self.btn_conectar_wifi.setEnabled(False)

        def _worker_wifi():
            sucesso, msg = conectar_wifi_nmcli(ssid, senha)
            if sucesso:
                if testar_conexao_internet(timeout=4):
                    self.sinal_wifi_finalizado.emit(True, f"Conectado à rede {ssid} com sucesso!")
                else:
                    self.sinal_wifi_finalizado.emit(False, f"Conectado ao Wi-Fi ({ssid}), mas sem acesso à internet.")
            else:
                self.sinal_wifi_finalizado.emit(False, msg)

        threading.Thread(target=_worker_wifi, daemon=True).start()

    @pyqtSlot(bool, str)
    def ao_concluir_conexao_wifi(self, sucesso, mensagem):
        self.btn_conectar_wifi.setEnabled(True)
        if sucesso:
            ssid_atual = self.input_ssid.text().strip()
            self.preparar_leitura(
                "SINCRONIZAR_GIT_MESTRE",
                f"Conectado à rede: {ssid_atual}\n\nAproxime o CRACHÁ MESTRE para autorizar a Sincronização"
            )
        else:
            self.lbl_wifi_status.setText(f"Falha: {mensagem}\nTente novamente ou volte ao menu.")
            self.lbl_wifi_status.setStyleSheet("color: #C62828; font-weight: bold;")

    def iniciar_sincronizacao_git(self):
        self.mudar_tela(self.tela_status_rede, "SINCRONIZANDO_GIT")
        self.lbl_status_rede_detalhe.setText("Sincronizando checklists com o Git...\nAguarde envio dos arquivos...")
        self.lbl_status_rede_detalhe.setStyleSheet(
            "color: #1565C0; padding: 15px; border: 2px solid #1565C0; border-radius: 10px; background-color: #E3F2FD;"
        )
        self.container_btn_rede.setEnabled(False)
        threading.Thread(target=self._worker_sincronizar_git, daemon=True).start()

    def _worker_sincronizar_git(self):
        try:
            os.makedirs(PASTA_CHECKLISTS, exist_ok=True)

            # 1. Adicionar PDFs e planilha alterada ao git
            subprocess.run(["git", "add", "checklists/.", "Lista_Basedecrachás.xlsx"], check=True, capture_output=True, text=True, timeout=10)

            # 2. Criar commit
            msg_commit = f"Sincronização manual - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            res_commit = subprocess.run(["git", "commit", "-m", msg_commit], capture_output=True, text=True, timeout=10)

            # 3. Fazer o Push para o repositório remoto
            res_push = subprocess.run(["git", "push"], capture_output=True, text=True, timeout=20)

            if res_push.returncode == 0:
                if "nothing to commit" in res_commit.stdout or "nothing to commit" in res_commit.stderr:
                    self.sinal_git_finalizado.emit(True, "Nenhum checklist novo para enviar.\nGit já atualizado!")
                else:
                    self.sinal_git_finalizado.emit(True, "Checklists e Dados Enviados ao Git com Sucesso!")
            else:
                self.sinal_git_finalizado.emit(False, f"Erro no Git Push:\n{res_push.stderr[:120]}")

        except subprocess.TimeoutExpired:
            self.sinal_git_finalizado.emit(False, "Tempo limite excedido na conexão com o servidor Git.")
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr if e.stderr else str(e)
            self.sinal_git_finalizado.emit(False, f"Falha no Git:\n{err_msg[:120]}")
        except Exception as e:
            self.sinal_git_finalizado.emit(False, f"Erro inesperado:\n{str(e)[:120]}")

    @pyqtSlot(bool, str)
    def ao_concluir_sincronizacao_git(self, sucesso, mensagem):
        self.container_btn_rede.setEnabled(True)

        if sucesso:
            self.lbl_status_rede_detalhe.setText(f"SINCRONIZAÇÃO CONCLUÍDA!\n\n{mensagem}")
            self.lbl_status_rede_detalhe.setStyleSheet(
                "color: #1B5E20; padding: 15px; border: 2px solid #2E7D32; border-radius: 10px; background-color: #E8F5E9;"
            )
            QTimer.singleShot(4000, lambda: self.mudar_tela(self.tela_liberar_gt, "MENU_GT"))
        else:
            self.lbl_status_rede_detalhe.setText(f"FALHA NA SINCRONIZAÇÃO GIT\n\n{mensagem}")
            self.lbl_status_rede_detalhe.setStyleSheet(
                "color: #C62828; padding: 15px; border: 2px solid #C62828; border-radius: 10px; background-color: #FFEBEE;"
            )

    # ========================================================================
    # TELA DE LEITURA RFID
    # ========================================================================
    def criar_tela_leitura(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(12)

        lbl_hdr = self.criar_widget_cabecalho()

        self.lbl_instrucao = QtWidgets.QLabel("Aproxime o seu crachá...")
        self.lbl_instrucao.setFont(QFont("Arial", 17, QFont.Bold))
        self.lbl_instrucao.setAlignment(Qt.AlignCenter)
        self.lbl_instrucao.setStyleSheet("color: #212121; margin-top: 5px; margin-bottom: 10px;")

        self.lbl_status = QtWidgets.QLabel("Aguardando leitura do leitor RFID...")
        self.lbl_status.setFont(QFont("Arial", 15, QFont.Bold))
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(
            "color: #424242; padding: 20px; border: 2px dashed #BDBDBD; border-radius: 12px; background-color: #FFFFFF;"
        )
        self.lbl_status.setFixedSize(650, 160)

        btn_cancelar = QtWidgets.QPushButton("CANCELAR")
        btn_cancelar.setFont(QFont("Arial", 14, QFont.Bold))
        btn_cancelar.setFixedSize(260, 50)
        btn_cancelar.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                border-radius: 8px;
                margin-top: 10px;
            }
            QPushButton:pressed {
                background-color: #424242;
            }
        """)
        btn_cancelar.clicked.connect(lambda: self.mudar_tela(self.tela_liberar_gt, "MENU_GT"))

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl_instrucao)
        layout.addWidget(self.lbl_status, alignment=Qt.AlignCenter)
        layout.addWidget(btn_cancelar, alignment=Qt.AlignCenter)

        tela.setLayout(layout)
        return tela

    def preparar_leitura(self, estado, instrucao):
        self.lbl_instrucao.setText(instrucao)
        self.lbl_status.setText("Aguardando leitura do leitor RFID...")
        self.lbl_status.setStyleSheet(
            "color: #424242; padding: 20px; border: 2px dashed #BDBDBD; border-radius: 12px; background-color: #FFFFFF;"
        )
        self.mudar_tela(self.tela_leitura, estado)

    def mostrar_mensagem(self, texto, cor_fundo, cor_texto):
        self.lbl_status.setText(texto)
        self.lbl_status.setStyleSheet(
            f"color: {cor_texto}; padding: 15px; border: 2px solid {cor_fundo}; border-radius: 12px; background-color: {cor_fundo}; font-weight: bold;"
        )
        QTimer.singleShot(3000, lambda: self.mudar_tela(self.tela_liberar_gt, "MENU_GT"))

    # ========================================================================
    # CHECKLIST
    # ========================================================================
    def criar_bloco_pergunta(self, idx_pergunta):
        container = QtWidgets.QWidget()
        container.setAttribute(Qt.WA_TranslucentBackground)
        container.setStyleSheet("background-color: transparent;")
        container.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        lbl_p = QtWidgets.QLabel(f"{idx_pergunta + 1}. {self.perguntas[idx_pergunta]}")
        lbl_p.setFont(QFont("Arial", 14, QFont.Bold))
        lbl_p.setWordWrap(True)
        lbl_p.setAlignment(Qt.AlignCenter)
        lbl_p.setStyleSheet("background-color: transparent; color: #111111; padding: 0;")

        h_btn = QtWidgets.QHBoxLayout()
        h_btn.setSpacing(16)
        h_btn.setAlignment(Qt.AlignCenter)

        btn_ok = QtWidgets.QPushButton("OK")
        btn_ok.setFont(QFont("Arial", 14, QFont.Bold))
        btn_ok.setFixedSize(170, 46)
        btn_ok.setStyleSheet(
            "background-color: #E8F5E9; color: #2E7D32; border: 2px solid #2E7D32; border-radius: 8px;"
        )

        btn_nok = QtWidgets.QPushButton("NÃO OK")
        btn_nok.setFont(QFont("Arial", 14, QFont.Bold))
        btn_nok.setFixedSize(170, 46)
        btn_nok.setStyleSheet(
            "background-color: #FFEBEE; color: #C62828; border: 2px solid #C62828; border-radius: 8px;"
        )

        btn_ok.clicked.connect(lambda: self.selecionar_resposta(idx_pergunta, "OK", btn_ok, btn_nok))
        btn_nok.clicked.connect(lambda: self.selecionar_resposta(idx_pergunta, "NÃO OK", btn_ok, btn_nok))

        h_btn.addWidget(btn_ok)
        h_btn.addWidget(btn_nok)

        layout.addWidget(lbl_p)
        layout.addLayout(h_btn)
        return container

    def selecionar_resposta(self, idx, valor, btn_ok, btn_nok):
        self.respostas_checklist[idx] = valor
        if valor == "OK":
            btn_ok.setStyleSheet(
                "background-color: #2E7D32; color: white; border: 2px solid #2E7D32; border-radius: 8px;"
            )
            btn_nok.setStyleSheet(
                "background-color: #FFEBEE; color: #C62828; border: 2px solid #C62828; border-radius: 8px;"
            )
        else:
            btn_nok.setStyleSheet(
                "background-color: #C62828; color: white; border: 2px solid #C62828; border-radius: 8px;"
            )
            btn_ok.setStyleSheet(
                "background-color: #E8F5E9; color: #2E7D32; border: 2px solid #2E7D32; border-radius: 8px;"
            )

    def criar_tela_par_perguntas(self, idx1, idx2):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tela)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        lbl_hdr = self.criar_widget_cabecalho()

        header = QtWidgets.QLabel("CHECKLIST DE SEGURANÇA")
        header.setFont(QFont("Arial", 14, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #1A237E; background-color: transparent;")

        bloco1 = self.criar_bloco_pergunta(idx1)
        bloco2 = self.criar_bloco_pergunta(idx2)

        botoes_nav = QtWidgets.QHBoxLayout()
        botoes_nav.setSpacing(12)

        style_btn_nav = """
            QPushButton {{
                background-color: {cor};
                color: white;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13pt;
            }}
            QPushButton:pressed {{
                background-color: {cor_press};
            }}
        """

        btn_voltar = QtWidgets.QPushButton("◄ ANTERIOR")
        btn_voltar.setFixedHeight(46)
        btn_voltar.setStyleSheet(style_btn_nav.format(cor="#757575", cor_press="#424242"))

        idx_tela_atual = idx1 // 2
        if idx_tela_atual == 0:
            btn_voltar.clicked.connect(lambda: self.mudar_tela(self.tela_liberar_gt, "MENU_GT"))
        else:
            btn_voltar.clicked.connect(lambda: self.mudar_tela(self.telas_checklist_perguntas[idx_tela_atual - 1],
                                                               f"CHK_PAG_{idx_tela_atual - 1}"))

        btn_proximo = QtWidgets.QPushButton("PRÓXIMO ►")
        btn_proximo.setFixedHeight(46)
        btn_proximo.setStyleSheet(style_btn_nav.format(cor="#1565C0", cor_press="#0D47A1"))
        btn_proximo.clicked.connect(lambda: self.validar_e_avancar_pagina(idx_tela_atual))

        botoes_nav.addWidget(btn_voltar)
        botoes_nav.addWidget(btn_proximo)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(header, alignment=Qt.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(bloco1, alignment=Qt.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(bloco2, alignment=Qt.AlignCenter)
        layout.addStretch(1)
        layout.addLayout(botoes_nav)
        return tela

    def criar_tela_pergunta_final(self, idx_pergunta):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tela)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        lbl_hdr = self.criar_widget_cabecalho()

        header = QtWidgets.QLabel("CHECKLIST DE SEGURANÇA - FINALIZAÇÃO")
        header.setFont(QFont("Arial", 14, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #1A237E; background-color: transparent;")

        bloco1 = self.criar_bloco_pergunta(idx_pergunta)

        botoes_nav = QtWidgets.QHBoxLayout()
        botoes_nav.setSpacing(12)

        style_btn_nav = """
            QPushButton {{
                background-color: {cor};
                color: white;
                border-radius: 8px;
                font-weight: bold;
                font-size: 13pt;
            }}
            QPushButton:pressed {{
                background-color: {cor_press};
            }}
        """

        btn_voltar = QtWidgets.QPushButton("◄ ANTERIOR")
        btn_voltar.setFixedHeight(46)
        btn_voltar.setStyleSheet(style_btn_nav.format(cor="#757575", cor_press="#424242"))
        btn_voltar.clicked.connect(lambda: self.mudar_tela(self.telas_checklist_perguntas[4], "CHK_PAG_4"))

        btn_concluir = QtWidgets.QPushButton("CONCLUIR CHECKLIST")
        self.btn_concluir_checklist = btn_concluir
        btn_concluir.setFixedHeight(46)
        btn_concluir.setStyleSheet(style_btn_nav.format(cor="#2E7D32", cor_press="#1B5E20"))
        btn_concluir.clicked.connect(self.processar_finalizacao_checklist)

        botoes_nav.addWidget(btn_voltar)
        botoes_nav.addWidget(btn_concluir)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(header, alignment=Qt.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(bloco1, alignment=Qt.AlignCenter)
        layout.addStretch(1)
        layout.addLayout(botoes_nav)
        return tela

    def validar_e_avancar_pagina(self, pagina_index):
        p1 = pagina_index * 2
        p2 = p1 + 1

        if p1 not in self.respostas_checklist or p2 not in self.respostas_checklist:
            QtWidgets.QMessageBox.warning(self, "Atenção", "Responda a ambas as perguntas para avançar.")
            return

        self.mudar_tela(self.telas_checklist_perguntas[pagina_index + 1], f"CHK_PAG_{pagina_index + 1}")

    # ========================================================================
    # TELAS DE STATUS
    # ========================================================================
    def criar_tela_aprovado(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignCenter)

        lbl_titulo = QtWidgets.QLabel("EQUIPAMENTO LIBERADO")
        lbl_titulo.setFont(QFont("Arial", 18, QFont.Bold))
        lbl_titulo.setAlignment(Qt.AlignCenter)
        lbl_titulo.setStyleSheet("color: #2E7D32;")

        self.lbl_msg_aprovado = QtWidgets.QLabel("Checklist Aprovado com Sucesso!")
        self.lbl_msg_aprovado.setFont(QFont("Arial", 14, QFont.Bold))
        self.lbl_msg_aprovado.setAlignment(Qt.AlignCenter)
        self.lbl_msg_aprovado.setWordWrap(True)

        self.lbl_tempo_restante = QtWidgets.QLabel("03:00")
        self.lbl_tempo_restante.setFont(QFont("Arial", 32, QFont.Bold))
        self.lbl_tempo_restante.setAlignment(Qt.AlignCenter)
        self.lbl_tempo_restante.setStyleSheet(
            "color: #1B5E20; background-color: #E8F5E9; border: 2px solid #2E7D32; border-radius: 12px; padding: 12px 24px;"
        )

        btn_voltar_menu = QtWidgets.QPushButton("Voltar ao Menu Principal")
        btn_voltar_menu.setFont(QFont("Arial", 13, QFont.Bold))
        btn_voltar_menu.setFixedHeight(48)
        btn_voltar_menu.setFixedWidth(400)
        btn_voltar_menu.setStyleSheet("""
            QPushButton {
                background-color: #0288D1;
                color: white;
                border-radius: 8px;
            }
            QPushButton:pressed {
                background-color: #01579B;
            }
        """)
        btn_voltar_menu.clicked.connect(self.finalizar_tempo_liberacao)

        layout.addWidget(lbl_titulo, alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl_msg_aprovado, alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl_tempo_restante, alignment=Qt.AlignCenter)
        layout.addWidget(btn_voltar_menu, alignment=Qt.AlignCenter)

        return widget

    def criar_tela_reprovado_bloqueado(self):
        tela = QtWidgets.QWidget()
        tela.setStyleSheet("background-color: #C62828;")

        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(18)

        lbl_hdr = self.criar_widget_cabecalho()

        lbl_msg = QtWidgets.QLabel("Checklist Reprovado\nContate a Segurança / Manutenção")
        lbl_msg.setFont(QFont("Arial", 20, QFont.Bold))
        lbl_msg.setStyleSheet("color: white;")
        lbl_msg.setAlignment(Qt.AlignCenter)

        lbl_trava = QtWidgets.QLabel("SISTEMA BLOQUEADO\nAproxime o Crachá MESTRE para desbloquear")
        lbl_trava.setFont(QFont("Arial", 15, QFont.Bold))
        lbl_trava.setStyleSheet("color: #FFEBEE;")
        lbl_trava.setAlignment(Qt.AlignCenter)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(lbl_msg)
        layout.addWidget(lbl_trava)
        tela.setLayout(layout)
        return tela

    def criar_tela_processando_checklist(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tela)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl = QtWidgets.QLabel("Finalizando checklist...\nAguarde, gerando o registro.")
        lbl.setFont(QFont("Arial", 20, QFont.Bold))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #1A237E; background-color: transparent;")
        layout.addWidget(lbl, alignment=Qt.AlignCenter)
        return tela

    def criar_tela_confirmacao_operacao(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tela)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)

        self.lbl_confirmacao_operacao = QtWidgets.QLabel()
        self.lbl_confirmacao_operacao.setFont(QFont("Arial", 20, QFont.Bold))
        self.lbl_confirmacao_operacao.setAlignment(Qt.AlignCenter)
        self.lbl_confirmacao_operacao.setStyleSheet("color: white; background-color: transparent;")
        self.lbl_confirmacao_operacao.setWordWrap(True)
        layout.addWidget(self.lbl_confirmacao_operacao, alignment=Qt.AlignCenter)
        return tela

    def mostrar_confirmacao_operacao(self, texto, cor_fundo):
        self.tela_confirmacao_operacao.setStyleSheet(f"background-color: {cor_fundo};")
        self.lbl_confirmacao_operacao.setText(texto)
        self.mudar_tela(self.tela_confirmacao_operacao, "CONFIRMACAO_OPERACAO")
        QTimer.singleShot(3000, lambda: self.mudar_tela(self.tela_liberar_gt, "MENU_GT"))

    # ========================================================================
    # PROCESSAMENTO DE CHECKLIST E LIBERAÇÃO
    # ========================================================================
    def iniciar_checklist_para_usuario(self, func_dados):
        self.operador_atual = func_dados
        self.respostas_checklist.clear()
        self.finalizacao_em_andamento = False
        if hasattr(self, "btn_concluir_checklist"):
            self.btn_concluir_checklist.setEnabled(True)

        for tela in self.telas_checklist_perguntas:
            for btn in tela.findChildren(QtWidgets.QPushButton):
                if btn.text() == "OK":
                    btn.setStyleSheet(
                        "background-color: #E8F5E9; color: #2E7D32; border: 2px solid #2E7D32; border-radius: 8px;"
                    )
                elif btn.text() == "NÃO OK":
                    btn.setStyleSheet(
                        "background-color: #FFEBEE; color: #C62828; border: 2px solid #C62828; border-radius: 8px;"
                    )

        self.mudar_tela(self.telas_checklist_perguntas[0], "CHK_PAG_0")

    def processar_finalizacao_checklist(self):
        if self.finalizacao_em_andamento:
            return

        self.finalizacao_em_andamento = True
        total_perguntas = len(self.perguntas)

        if len(self.respostas_checklist) != total_perguntas:
            QtWidgets.QMessageBox.warning(
                self,
                "Atenção",
                "Responda a todas as perguntas antes de concluir o checklist."
            )
            self.finalizacao_em_andamento = False
            return

        if self.operador_atual is None:
            QtWidgets.QMessageBox.warning(self, "Atenção", "Nenhum operador identificado.")
            self.finalizacao_em_andamento = False
            self.mudar_tela(self.tela_liberar_gt, "MENU_GT")
            return

        respostas_lista = [self.respostas_checklist[i] for i in range(total_perguntas)]
        reprovado = "NÃO OK" in respostas_lista

        dados_checklist = {
            'operador': self.operador_atual['nome'],
            'matricula': self.operador_atual['matricula'],
            'equipamento': "1172",
            'data': datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            'respostas': respostas_lista,
            'obs': "Sem observações.",
            'status': "REPROVADO" if reprovado else "APROVADO"
        }

        if hasattr(self, 'btn_concluir_checklist'):
            self.btn_concluir_checklist.setEnabled(False)

        self._aplicar_resultado_checklist(dados_checklist)

        self.thread_finalizacao = threading.Thread(
            target=self._gerar_pdf_em_background,
            args=(dados_checklist,),
            daemon=True
        )
        self.thread_finalizacao.start()

    def _aplicar_resultado_checklist(self, dados_checklist):
        if dados_checklist['status'] == "APROVADO":
            turno_atual = self.obter_turno_atual()
            if turno_atual not in self.checklists_aprovados_turno:
                self.checklists_aprovados_turno[turno_atual] = set()
            self.checklists_aprovados_turno[turno_atual].add(dados_checklist['matricula'])
            self.liberar_equipamento_por_3min(
                dados_checklist['matricula'],
                dados_checklist['operador']
            )
        else:
            self.invalidar_checklists_do_turno()
            self.mudar_tela(self.tela_reprovado_bloqueado, "SISTEMA_BLOQUEADO")

    def _gerar_pdf_em_background(self, dados_checklist):
        try:
            pdf_path = self.gerar_pdf_checklist(dados_checklist)
            if pdf_path:
                print(f"[CHECKLIST] PDF gerado com sucesso: {pdf_path}")
        except Exception as erro:
            print(f"[CHECKLIST] Erro ao gerar registro PDF: {erro}")

    def liberar_equipamento_por_3min(self, matricula, nome):
        self.timer_liberacao.stop()
        self.timer_cronometro.stop()
        set_gpios(1)
        self.fim_liberacao = time.monotonic() + TEMPO_LIBERACAO_SEGUNDOS
        self.lbl_msg_aprovado.setText(f"Checklist Aprovado:\n[{matricula}] {nome}")
        self.mudar_tela(self.tela_aprovado, "EQUIPAMENTO_LIBERADO")
        self.atualizar_cronometro_liberacao()
        self.timer_cronometro.start(1000)
        self.timer_liberacao.start(TEMPO_LIBERACAO_SEGUNDOS * 1000)

    def finalizar_tempo_liberacao(self):
        self.timer_liberacao.stop()
        self.timer_cronometro.stop()
        self.fim_liberacao = None
        self.finalizacao_em_andamento = False

        if hasattr(self, 'btn_concluir_checklist'):
            self.btn_concluir_checklist.setEnabled(True)

        if hasattr(self, 'lbl_tempo_restante'):
            self.lbl_tempo_restante.setText("00:00:00")

        set_gpios(0)
        self.mudar_tela(self.tela_liberar_gt, "MENU_GT")

    # ========================================================================
    # PROCESSAMENTO DE LEITURA RFID
    # ========================================================================
    @pyqtSlot(str)
    def processar_rfid(self, uid):
        agora = time.time()
        uid_clean = str(uid).strip()

        if self.uid_bloqueado_ate_novo_cracha is not None:
            if uid_clean == self.uid_bloqueado_ate_novo_cracha:
                return
            print(f"[RFID] Novo crachá detectado: {uid_clean}. Liberando próxima etapa.")
            self.uid_bloqueado_ate_novo_cracha = None

        if uid_clean == self.ultimo_uid_lido and (agora - self.tempo_ultimo_lido) < 1.0:
            return

        self.ultimo_uid_lido = uid_clean
        self.tempo_ultimo_lido = agora

        print(f"[PROCESSAR RFID] UID Lido: {uid_clean} | Estado: {self.estado_atual}")

        if self.estado_atual == "SISTEMA_BLOQUEADO":
            if uid_clean == UID_MESTRE:
                print("✓ Sistema desbloqueado com Crachá Mestre!")
                self.mudar_tela(self.tela_liberar_gt, "MENU_GT")
            return

        if self.central_widget.currentWidget() != self.tela_leitura:
            return

        if self.estado_atual == "SINCRONIZAR_GIT_MESTRE":
            if uid_clean == UID_MESTRE:
                self.iniciar_sincronizacao_git()
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não é Mestre!", "#C62828", "white")

        elif self.estado_atual == "LIBERAR_EQUIPAMENTO":
            func = self.dados.buscar_por_cracha(uid_clean)
            if not func:
                self.mostrar_mensagem("ACESSO NEGADO\n\nCrachá não cadastrado!", "#C62828", "white")
                return

            if func['status'] != 'H':
                self.mostrar_mensagem(f"ACESSO NEGADO\n\nUsuário Desabilitado!\n{func['nome']}", "#C62828", "white")
                return

            turno_atual = self.obter_turno_atual()
            aprovados_no_turno = self.checklists_aprovados_turno.get(turno_atual, set())

            if func['matricula'] in aprovados_no_turno:
                self.liberar_equipamento_por_3min(func['matricula'], func['nome'])
            else:
                self.iniciar_checklist_para_usuario(func)

        elif self.estado_atual == "HABILITAR_USUARIO_MESTRE":
            if uid_clean == UID_MESTRE:
                self.estado_atual = "HABILITAR_USUARIO_FINAL"
                self.uid_bloqueado_ate_novo_cracha = UID_MESTRE
                self.lbl_instrucao.setText("Aproxime o crachá do USUÁRIO")
                self.lbl_status.setText("✓ Mestre Autorizado!\n\nRetire o crachá mestre e aproxime o do Usuário...")
                self.lbl_status.setStyleSheet(
                    "color: #1B5E20; padding: 15px; border: 2px solid #2E7D32; border-radius: 12px; font-weight: bold; background-color: #E8F5E9;"
                )
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não é Mestre!", "#C62828", "white")

        elif self.estado_atual == "HABILITAR_USUARIO_FINAL":
            if uid_clean == UID_MESTRE:
                print("[RFID] Crachá Mestre detectado novamente. Aguardando crachá do Usuário...")
                return

            func = self.dados.buscar_por_cracha(uid_clean)
            if func:
                if self.dados.alterar_status(uid_clean, 'H'):
                    self.mostrar_confirmacao_operacao("Usuário habilitado", "#2E7D32")
                else:
                    self.mostrar_mensagem("ERRO\n\nFalha ao atualizar planilha!", "#C62828", "white")
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não encontrado!", "#C62828", "white")

        elif self.estado_atual == "DESABILITAR_USUARIO_MESTRE":
            if uid_clean == UID_MESTRE:
                self.estado_atual = "DESABILITAR_USUARIO_FINAL"
                self.uid_bloqueado_ate_novo_cracha = UID_MESTRE
                self.lbl_instrucao.setText("Aproxime o crachá do USUÁRIO")
                self.lbl_status.setText("✓ Mestre Autorizado!\n\nRetire o crachá mestre e aproxime o do Usuário...")
                self.lbl_status.setStyleSheet(
                    "color: #1B5E20; padding: 15px; border: 2px solid #2E7D32; border-radius: 12px; font-weight: bold; background-color: #E8F5E9;"
                )
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não é Mestre!", "#C62828", "white")

        elif self.estado_atual == "DESABILITAR_USUARIO_FINAL":
            if uid_clean == UID_MESTRE:
                print("[RFID] Crachá Mestre detectado novamente. Aguardando crachá do Usuário...")
                return

            func = self.dados.buscar_por_cracha(uid_clean)
            if func:
                if self.dados.alterar_status(uid_clean, 'D'):
                    self.mostrar_confirmacao_operacao("Usuário desabilitado", "#C62828")
                else:
                    self.mostrar_mensagem("ERRO\n\nFalha ao atualizar planilha!", "#C62828", "white")
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não encontrado!", "#C62828", "white")

    # ========================================================================
    # GERADOR DE PDF
    # ========================================================================
    def gerar_pdf_checklist(self, dados):
        try:
            os.makedirs(PASTA_CHECKLISTS, exist_ok=True)
            nome_arq = f"checklist_{dados['operador'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            arquivo_pdf = os.path.join(PASTA_CHECKLISTS, nome_arq)

            doc = SimpleDocTemplate(arquivo_pdf, pagesize=letter, topMargin=0.4 * inch, bottomMargin=0.4 * inch,
                                    leftMargin=0.4 * inch, rightMargin=0.4 * inch)
            story = []
            styles = getSampleStyleSheet()

            style_titulo = ParagraphStyle('Titulo', parent=styles['Heading1'], fontSize=15,
                                          textColor=colors.HexColor('#1A237E'), alignment=1, spaceAfter=10)

            story.append(Paragraph("CHECKLIST DE SEGURANÇA - GUINCHO TRACIONADOR", style_titulo))
            story.append(Spacer(1, 0.1 * inch))

            info_table = Table([
                ["Operador:", dados['operador'], "Matrícula:", dados['matricula']],
                ["Equipamento:", dados['equipamento'], "Data/Hora:", dados['data']],
                ["Status:", dados['status'], "", ""]
            ], colWidths=[1.2 * inch, 2.8 * inch, 1.2 * inch, 2.3 * inch])

            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F5F5F5')),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))

            story.append(info_table)
            story.append(Spacer(1, 0.15 * inch))

            perguntas_data = []
            for i, (pergunta, resposta) in enumerate(zip(self.perguntas, dados['respostas']), 1):
                p_para = Paragraph(f"<b>{i}.</b> {pergunta}",
                                   ParagraphStyle('P', parent=styles['Normal'], fontSize=8.5, leading=11))
                resp_text = "✓ OK" if resposta == "OK" else "✗ NÃO OK"
                perguntas_data.append([p_para, resp_text])

            t_perguntas = Table(perguntas_data, colWidths=[6.0 * inch, 1.5 * inch])
            t_perguntas.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8.5),
                ('PADDING', (0, 0), (-1, -1), 5),
                ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#FAFAFA')])
            ]))

            story.append(t_perguntas)

            doc.build(story)
            return arquivo_pdf
        except Exception as e:
            print(f"✗ Erro ao gerar PDF: {e}")
            return None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F4 and event.modifiers() & Qt.AltModifier:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.timer_liberacao.stop()
        self.timer_cronometro.stop()
        self.fim_liberacao = None
        set_gpios(0)
        self.leitor_rfid.parar()
        event.accept()


# ============================================================================
# EXECUÇÃO DA APLICAÇÃO
# ============================================================================
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = SistemaGT()
    window.show()
    sys.exit(app.exec_())