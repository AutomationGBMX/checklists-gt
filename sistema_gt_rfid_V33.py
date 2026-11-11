#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema Completo de Controle de Acesso GBMX e Checklist de Segurança - Liberar GT
Otimizado para Tela Raspberry Pi de 5 Polegadas (800x480)
Versão 36 - Níveis de Acesso (Mestre Principal, Mestre Nível 2 e Usuário Comum)
"""

import sys
import os
import re
import json
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

PASTA_APLICACAO = os.path.dirname(os.path.realpath(__file__))
PASTA_CHECKLISTS = os.path.join(PASTA_APLICACAO, "checklists")
ARQUIVO_CONFIG = os.path.join(PASTA_APLICACAO, "configuracoes.json")
ARQUIVO_PLANILHA = os.path.join(PASTA_APLICACAO, "Lista_Basedecrachás.xlsx")
TEMPO_LIBERACAO_SEGUNDOS_PADRAO = 180

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
        result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True, timeout=2)
        ssid = result.stdout.strip()
        if ssid:
            return ssid

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
        subprocess.run(["nmcli", "connection", "delete", "id", ssid], capture_output=True, timeout=5)

        if senha:
            cmd = ["nmcli", "dev", "wifi", "connect", ssid, "password", senha]
        else:
            cmd = ["nmcli", "dev", "wifi", "connect", ssid]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if res.returncode == 0 or "successfully activated" in res.stdout.lower():
            return True, "Conectado com sucesso!"
        else:
            if "key-mgmt" in res.stderr.lower() or "key-mgmt" in res.stdout.lower():
                subprocess.run(["nmcli", "connection", "delete", "id", ssid], capture_output=True, timeout=5)
                if senha:
                    cmd_add = [
                        "nmcli", "con", "add", "type", "wifi", "con-name", ssid,
                        "ssid", ssid, "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", senha
                    ]
                else:
                    cmd_add = [
                        "nmcli", "con", "add", "type", "wifi", "con-name", ssid,
                        "ssid", ssid
                    ]
                subprocess.run(cmd_add, capture_output=True, text=True, timeout=10)
                res_up = subprocess.run(["nmcli", "con", "up", "id", ssid], capture_output=True, text=True, timeout=15)
                if res_up.returncode == 0 or "successfully activated" in res_up.stdout.lower():
                    return True, "Conectado com sucesso!"

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
    def __init__(self, arquivo_excel=ARQUIVO_PLANILHA):
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
    sinal_pdf_publicado = pyqtSignal(bool, str)
    sinal_wifi_finalizado = pyqtSignal(bool, str)
    sinal_diagnostico_rede = pyqtSignal(bool, bool, str)

    def __init__(self):
        super().__init__()

        self.dados = GerenciadorDados()
        self.carregar_configuracao()

        self.labels_data_hora = []
        self.checklists_aprovados_turno = {}

        self.operador_atual = None
        self.mestre_n2_atual = None
        self.msg_temporaria_ate = 0
        self.origem_voltar_leitura = "TELA_PRINCIPAL"

        self.respostas_checklist = {}
        self.finalizacao_em_andamento = False
        self.thread_finalizacao = None
        self.git_lock = threading.Lock()

        self.ultimo_uid_lido = None
        self.tempo_ultimo_lido = 0
        self.uid_bloqueado_ate_novo_cracha = None

        # Conectar sinais
        self.sinal_git_finalizado.connect(self.ao_concluir_sincronizacao_git)
        self.sinal_pdf_publicado.connect(self.ao_concluir_publicacao_pdf)
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

    def carregar_configuracao(self):
        """Carrega o tempo de liberação configurado a partir de um arquivo JSON local."""
        self.tempo_liberacao_segundos = TEMPO_LIBERACAO_SEGUNDOS_PADRAO
        try:
            if os.path.exists(ARQUIVO_CONFIG):
                with open(ARQUIVO_CONFIG, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    self.tempo_liberacao_segundos = int(cfg.get('tempo_liberacao', TEMPO_LIBERACAO_SEGUNDOS_PADRAO))
                    print(f"✓ Configuração carregada: Tempo de Liberação = {self.tempo_liberacao_segundos}s")
        except Exception as e:
            print(f"[CONFIG] Erro ao carregar configuracao: {e}")

    def salvar_configuracao(self, novo_tempo_segundos):
        """Salva persistentemente o novo tempo de liberação no arquivo JSON."""
        try:
            self.tempo_liberacao_segundos = int(novo_tempo_segundos)
            with open(ARQUIVO_CONFIG, 'w', encoding='utf-8') as f:
                json.dump({'tempo_liberacao': self.tempo_liberacao_segundos}, f, indent=4)
            print(f"✓ Nova configuração salva: Tempo de Liberação = {self.tempo_liberacao_segundos}s")
            return True
        except Exception as e:
            print(f"[CONFIG] Erro ao salvar configuracao: {e}")
            return False

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
        lbl.setFont(QFont("Arial", 12, QFont.Bold))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #1A237E; background-color: #E8EAF6; padding: 4px 12px; border-radius: 6px;")
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
        str_tempo = f"{horas:02d}:{minutos:02d}:{segundos:02d}"

        if hasattr(self, 'lbl_tempo_restante'):
            self.lbl_tempo_restante.setText(str_tempo)

        if hasattr(self, 'lbl_status_main'):
            if time.time() >= self.msg_temporaria_ate:
                self.lbl_status_main.setText(
                    f"EQUIPAMENTO LIBERADO\n\nTempo restante: {str_tempo}\n\nAproxime o crachá para identificar"
                )
                self.lbl_status_main.setStyleSheet(
                    "color: #1B5E20; padding: 15px; border: 3px solid #2E7D32; border-radius: 12px; "
                    "background-color: #E8F5E9; font-weight: bold;"
                )

    def mostrar_mensagem_main(self, texto, cor_fundo, cor_texto, duracao_segs=3):
        """Exibe uma mensagem temporária na tela principal sem interromper o cronômetro ou o relé."""
        self.msg_temporaria_ate = time.time() + duracao_segs
        if hasattr(self, 'lbl_status_main'):
            self.lbl_status_main.setText(texto)
            self.lbl_status_main.setStyleSheet(
                f"color: {cor_texto}; padding: 15px; border: 2px solid {cor_fundo}; "
                f"border-radius: 12px; background-color: {cor_fundo}; font-weight: bold;"
            )

    def configurar_interface(self):
        self.setWindowTitle("SISTEMA GBMX - LIBERAR GT")
        self.setStyleSheet("background-color: #f4f4f9;")

        self.setFixedSize(800, 480)
        self.showFullScreen()

        self.central_widget = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.central_widget)

        self.tela_liberar_gt = self.criar_tela_menu_liberar_gt()
        self.tela_menu_mestre_principal = self.criar_tela_menu_mestre_principal()
        self.tela_menu_mestre_nivel2 = self.criar_tela_menu_mestre_nivel2()
        self.tela_selecao_nivel_habilitar = self.criar_tela_selecao_nivel_habilitar()

        self.tela_leitura = self.criar_tela_leitura()
        self.tela_wifi = self.criar_tela_wifi()
        self.tela_status_rede = self.criar_tela_status_rede()
        self.tela_configuracoes = self.criar_tela_configuracoes()

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
        self.central_widget.addWidget(self.tela_menu_mestre_principal)
        self.central_widget.addWidget(self.tela_menu_mestre_nivel2)
        self.central_widget.addWidget(self.tela_selecao_nivel_habilitar)
        self.central_widget.addWidget(self.tela_leitura)
        self.central_widget.addWidget(self.tela_wifi)
        self.central_widget.addWidget(self.tela_status_rede)
        self.central_widget.addWidget(self.tela_configuracoes)
        for t in self.telas_checklist_perguntas:
            self.central_widget.addWidget(t)
        self.central_widget.addWidget(self.tela_aprovado)
        self.central_widget.addWidget(self.tela_reprovado_bloqueado)
        self.central_widget.addWidget(self.tela_confirmacao_operacao)
        self.central_widget.addWidget(self.tela_processando_checklist)

        self.central_widget.setCurrentWidget(self.tela_liberar_gt)
        self.estado_atual = "TELA_PRINCIPAL"

    def mudar_tela(self, tela, novo_estado):
        self.estado_atual = novo_estado
        self.ultimo_uid_lido = None
        self.uid_bloqueado_ate_novo_cracha = None
        self.central_widget.setCurrentWidget(tela)

    # ========================================================================
    # TELA PRINCIPAL (REFORMULADA - REQUISITO 1)
    # ========================================================================
    def criar_tela_menu_liberar_gt(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(12)

        lbl_hdr = self.criar_widget_cabecalho()

        titulo = QtWidgets.QLabel("SISTEMA GBMX - CONTROLE DE ACESSO")
        titulo.setFont(QFont("Arial", 18, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("color: #1A237E;")

        lbl_instrucao = QtWidgets.QLabel("Aproxime o crachá para liberar o equipamento")
        lbl_instrucao.setFont(QFont("Arial", 17, QFont.Bold))
        lbl_instrucao.setAlignment(Qt.AlignCenter)
        lbl_instrucao.setStyleSheet("color: #0D47A1; margin-top: 4px; margin-bottom: 6px;")

        self.lbl_status_main = QtWidgets.QLabel("Aguardando leitura do crachá...")
        self.lbl_status_main.setFont(QFont("Arial", 16, QFont.Bold))
        self.lbl_status_main.setAlignment(Qt.AlignCenter)
        self.lbl_status_main.setWordWrap(True)
        self.lbl_status_main.setStyleSheet(
            "color: #424242; padding: 20px; border: 2px dashed #BDBDBD; border-radius: 12px; background-color: #FFFFFF;"
        )
        self.lbl_status_main.setFixedSize(720, 180)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(titulo, alignment=Qt.AlignCenter)
        layout.addWidget(lbl_instrucao, alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl_status_main, alignment=Qt.AlignCenter)

        tela.setLayout(layout)
        return tela

    # ========================================================================
    # MENU ADMINISTRATIVO - MESTRE PRINCIPAL (REQUISITO 3)
    # ========================================================================
    def criar_tela_menu_mestre_principal(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(15, 8, 15, 8)
        layout.setSpacing(8)

        lbl_hdr = self.criar_widget_cabecalho()

        titulo = QtWidgets.QLabel("MENU ADMINISTRATIVO - MESTRE PRINCIPAL")
        titulo.setFont(QFont("Arial", 18, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("color: #1A237E; margin-top: 2px; margin-bottom: 4px;")

        btn_style_base = """
            QPushButton {{
                background-color: {cor};
                color: white;
                border-radius: 10px;
                font-weight: bold;
                font-size: 15pt;
            }}
            QPushButton:pressed {{
                background-color: {cor_press};
            }}
        """

        btn_habilitar = QtWidgets.QPushButton("1 - HABILITAR USUÁRIO")
        btn_habilitar.setFixedSize(720, 52)
        btn_habilitar.setStyleSheet(btn_style_base.format(cor="#1565C0", cor_press="#0D47A1"))
        btn_habilitar.clicked.connect(self.abrir_selecao_nivel_habilitar)

        btn_desabilitar = QtWidgets.QPushButton("2 - DESABILITAR USUÁRIO")
        btn_desabilitar.setFixedSize(720, 52)
        btn_desabilitar.setStyleSheet(btn_style_base.format(cor="#C62828", cor_press="#8E0000"))
        btn_desabilitar.clicked.connect(
            lambda: self.preparar_leitura(
                "DESABILITAR_USUARIO",
                "Aproxime o crachá do USUÁRIO/MESTRE para DESABILITAR",
                origem_voltar="MENU_MESTRE_PRINCIPAL"
            )
        )

        btn_git = QtWidgets.QPushButton("3 - SINCRONIZAR CHECKLISTS (GIT)")
        btn_git.setFixedSize(720, 52)
        btn_git.setStyleSheet(btn_style_base.format(cor="#E65100", cor_press="#BF360C"))
        btn_git.clicked.connect(self.ao_clicar_opcao_git)

        btn_config = QtWidgets.QPushButton("4 - CONFIGURAÇÕES")
        btn_config.setFixedSize(720, 52)
        btn_config.setStyleSheet(btn_style_base.format(cor="#4A148C", cor_press="#311B92"))
        btn_config.clicked.connect(self.abrir_tela_configuracoes)

        btn_voltar = QtWidgets.QPushButton("VOLTAR / MENU PRINCIPAL")
        btn_voltar.setFixedSize(720, 48)
        btn_voltar.setStyleSheet(btn_style_base.format(cor="#757575", cor_press="#424242"))
        btn_voltar.clicked.connect(lambda: self.mudar_tela(self.tela_liberar_gt, "TELA_PRINCIPAL"))

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(titulo, alignment=Qt.AlignCenter)
        layout.addWidget(btn_habilitar, alignment=Qt.AlignCenter)
        layout.addWidget(btn_desabilitar, alignment=Qt.AlignCenter)
        layout.addWidget(btn_git, alignment=Qt.AlignCenter)
        layout.addWidget(btn_config, alignment=Qt.AlignCenter)
        layout.addWidget(btn_voltar, alignment=Qt.AlignCenter)

        tela.setLayout(layout)
        return tela

    # ========================================================================
    # SELEÇÃO DE NÍVEL PARA HABILITAÇÃO (REQUISITO 4)
    # ========================================================================
    def criar_tela_selecao_nivel_habilitar(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(12)

        lbl_hdr = self.criar_widget_cabecalho()

        titulo = QtWidgets.QLabel("HABILITAR USUÁRIO - SELEÇÃO DE NÍVEL")
        titulo.setFont(QFont("Arial", 18, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("color: #1A237E;")

        subtitulo = QtWidgets.QLabel("Selecione o nível de acesso para cadastrar:")
        subtitulo.setFont(QFont("Arial", 14, QFont.Bold))
        subtitulo.setAlignment(Qt.AlignCenter)

        btn_style = """
            QPushButton {{
                background-color: {cor};
                color: white;
                border-radius: 10px;
                font-weight: bold;
                font-size: 16pt;
            }}
            QPushButton:pressed {{
                background-color: {cor_press};
            }}
        """

        btn_comum = QtWidgets.QPushButton("1 - USUÁRIO COMUM")
        btn_comum.setFixedSize(720, 60)
        btn_comum.setStyleSheet(btn_style.format(cor="#1565C0", cor_press="#0D47A1"))
        btn_comum.clicked.connect(
            lambda: self.preparar_leitura(
                "HABILITAR_USUARIO_COMUM",
                "Aproxime o crachá do USUÁRIO COMUM para habilitar",
                origem_voltar="SELECAO_NIVEL"
            )
        )

        btn_m2 = QtWidgets.QPushButton("2 - MESTRE NÍVEL 2")
        btn_m2.setFixedSize(720, 60)
        btn_m2.setStyleSheet(btn_style.format(cor="#2E7D32", cor_press="#1B5E20"))
        btn_m2.clicked.connect(
            lambda: self.preparar_leitura(
                "HABILITAR_MESTRE_N2",
                "Aproxime o crachá do MESTRE NÍVEL 2 para habilitar",
                origem_voltar="SELECAO_NIVEL"
            )
        )

        btn_voltar = QtWidgets.QPushButton("VOLTAR")
        btn_voltar.setFixedSize(720, 50)
        btn_voltar.setStyleSheet(btn_style.format(cor="#757575", cor_press="#424242"))
        btn_voltar.clicked.connect(lambda: self.mudar_tela(self.tela_menu_mestre_principal, "MENU_MESTRE_PRINCIPAL"))

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(titulo, alignment=Qt.AlignCenter)
        layout.addWidget(subtitulo, alignment=Qt.AlignCenter)
        layout.addWidget(btn_comum, alignment=Qt.AlignCenter)
        layout.addWidget(btn_m2, alignment=Qt.AlignCenter)
        layout.addWidget(btn_voltar, alignment=Qt.AlignCenter)

        tela.setLayout(layout)
        return tela

    def abrir_selecao_nivel_habilitar(self):
        self.mudar_tela(self.tela_selecao_nivel_habilitar, "SELECAO_NIVEL")

    # ========================================================================
    # MENU - MESTRE NÍVEL 2 (REQUISITO 5)
    # ========================================================================
    def criar_tela_menu_mestre_nivel2(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(12)

        lbl_hdr = self.criar_widget_cabecalho()

        titulo = QtWidgets.QLabel("MENU - MESTRE NÍVEL 2")
        titulo.setFont(QFont("Arial", 18, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("color: #1A237E;")

        btn_style = """
            QPushButton {{
                background-color: {cor};
                color: white;
                border-radius: 10px;
                font-weight: bold;
                font-size: 16pt;
            }}
            QPushButton:pressed {{
                background-color: {cor_press};
            }}
        """

        btn_hab_comum = QtWidgets.QPushButton("1 - HABILITAR USUÁRIO COMUM")
        btn_hab_comum.setFixedSize(720, 60)
        btn_hab_comum.setStyleSheet(btn_style.format(cor="#1565C0", cor_press="#0D47A1"))
        btn_hab_comum.clicked.connect(
            lambda: self.preparar_leitura(
                "HABILITAR_USUARIO_COMUM_N2",
                "Aproxime o crachá do USUÁRIO COMUM para habilitar",
                origem_voltar="MENU_MESTRE_NIVEL2"
            )
        )

        btn_liberar = QtWidgets.QPushButton("2 - LIBERAR EQUIPAMENTO")
        btn_liberar.setFixedSize(720, 60)
        btn_liberar.setStyleSheet(btn_style.format(cor="#2E7D32", cor_press="#1B5E20"))
        btn_liberar.clicked.connect(self.iniciar_checklist_mestre_n2)

        btn_voltar = QtWidgets.QPushButton("VOLTAR / MENU PRINCIPAL")
        btn_voltar.setFixedSize(720, 50)
        btn_voltar.setStyleSheet(btn_style.format(cor="#757575", cor_press="#424242"))
        btn_voltar.clicked.connect(lambda: self.mudar_tela(self.tela_liberar_gt, "TELA_PRINCIPAL"))

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(titulo, alignment=Qt.AlignCenter)
        layout.addWidget(btn_hab_comum, alignment=Qt.AlignCenter)
        layout.addWidget(btn_liberar, alignment=Qt.AlignCenter)
        layout.addWidget(btn_voltar, alignment=Qt.AlignCenter)

        tela.setLayout(layout)
        return tela

    def iniciar_checklist_mestre_n2(self):
        if not self.mestre_n2_atual:
            self.mestre_n2_atual = {
                'nome': "Mestre Nível 2",
                'matricula': "M2_001",
                'status': "M2"
            }
        self.iniciar_checklist_para_usuario(self.mestre_n2_atual)

    # ========================================================================
    # CONFIGURAÇÕES DO SISTEMA
    # ========================================================================
    def criar_tela_configuracoes(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tela)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(6)

        lbl_hdr = self.criar_widget_cabecalho()

        titulo = QtWidgets.QLabel("CONFIGURAÇÕES DO SISTEMA")
        titulo.setFont(QFont("Arial", 15, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("color: #1A237E;")

        self.lbl_config_status = QtWidgets.QLabel()
        self.lbl_config_status.setFont(QFont("Arial", 13, QFont.Bold))
        self.lbl_config_status.setAlignment(Qt.AlignCenter)
        self.lbl_config_status.setStyleSheet("color: #212121;")

        form_layout = QtWidgets.QHBoxLayout()
        form_layout.setSpacing(10)

        lbl_tempo = QtWidgets.QLabel("Novo tempo (segundos):")
        lbl_tempo.setFont(QFont("Arial", 12, QFont.Bold))

        self.input_novo_tempo = QtWidgets.QLineEdit()
        self.input_novo_tempo.setFixedHeight(36)
        self.input_novo_tempo.setFont(QFont("Arial", 12))
        self.input_novo_tempo.setStyleSheet("background-color: white; border: 1px solid #777; border-radius: 6px; padding: 2px 8px;")

        form_layout.addWidget(lbl_tempo)
        form_layout.addWidget(self.input_novo_tempo, 1)

        self.teclado_config = TecladoVirtual()
        self.teclado_config.tecla_pressionada.connect(self.ao_digitar_teclado_config)

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

        btn_salvar = QtWidgets.QPushButton("SALVAR")
        btn_salvar.setFixedHeight(44)
        btn_salvar.setStyleSheet(btn_style_nav.format(cor="#2E7D32", cor_press="#1B5E20"))
        btn_salvar.clicked.connect(self.salvar_novas_configuracoes)

        btn_cancelar = QtWidgets.QPushButton("CANCELAR / VOLTAR")
        btn_cancelar.setFixedHeight(44)
        btn_cancelar.setStyleSheet(btn_style_nav.format(cor="#757575", cor_press="#424242"))
        btn_cancelar.clicked.connect(lambda: self.mudar_tela(self.tela_menu_mestre_principal, "MENU_MESTRE_PRINCIPAL"))

        btn_layout.addWidget(btn_cancelar)
        btn_layout.addWidget(btn_salvar)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(titulo, alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl_config_status, alignment=Qt.AlignCenter)
        layout.addLayout(form_layout)
        layout.addWidget(self.teclado_config)
        layout.addLayout(btn_layout)

        tela.setLayout(layout)
        return tela

    def abrir_tela_configuracoes(self):
        minutos = self.tempo_liberacao_segundos // 60
        segs = self.tempo_liberacao_segundos % 60
        str_tempo = f"{self.tempo_liberacao_segundos} seg"
        if minutos > 0:
            str_tempo += f" ({minutos} min {segs}s)" if segs else f" ({minutos} min)"

        self.lbl_config_status.setText(f"Tempo de liberação atual: {str_tempo}")
        self.input_novo_tempo.setText(str(self.tempo_liberacao_segundos))
        self.mudar_tela(self.tela_configuracoes, "TELA_CONFIGURACOES")

    def ao_digitar_teclado_config(self, valor):
        if valor == "BACKSPACE":
            self.input_novo_tempo.setText(self.input_novo_tempo.text()[:-1])
        elif valor == "CLEAR":
            self.input_novo_tempo.clear()
        elif valor.isdigit():
            self.input_novo_tempo.setText(self.input_novo_tempo.text() + valor)

    def salvar_novas_configuracoes(self):
        val_str = self.input_novo_tempo.text().strip()
        if not val_str.isdigit() or int(val_str) <= 0:
            QtWidgets.QMessageBox.warning(self, "Atenção", "Informe um tempo válido em segundos (inteiro maior que zero).")
            return

        novo_tempo = int(val_str)
        if self.salvar_configuracao(novo_tempo):
            self.mostrar_confirmacao_operacao(f"Tempo de liberação alterado para {novo_tempo} segundos", "#2E7D32")
        else:
            self.mostrar_mensagem("ERRO\n\nFalha ao salvar configurações!", "#C62828", "white")

    # ========================================================================
    # DIAGNÓSTICO DE REDE E GIT
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
        self.btn_voltar_rede.clicked.connect(lambda: self.mudar_tela(self.tela_menu_mestre_principal, "MENU_MESTRE_PRINCIPAL"))

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

        if not tem_wifi:
            self.lbl_wifi_status.setText("Nenhuma rede Wi-Fi conectada.\nInforme os dados da rede/hotspot:")
            self.lbl_wifi_status.setStyleSheet("color: #C62828; font-weight: bold; font-size: 13px;")
            self.mudar_tela(self.tela_wifi, "CONFIGURAR_WIFI")
            return

        if tem_wifi and tem_internet:
            self.iniciar_sincronizacao_git()
        else:
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

        self.teclado = TecladoVirtual()
        self.teclado.tecla_pressionada.connect(self.ao_digitar_teclado)

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
        btn_cancelar_wifi.clicked.connect(lambda: self.mudar_tela(self.tela_menu_mestre_principal, "MENU_MESTRE_PRINCIPAL"))

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
            self.iniciar_sincronizacao_git()
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
        with self.git_lock:
            self._worker_sincronizar_git_com_lock()

    def _worker_sincronizar_git_com_lock(self):
        try:
            repositorio = self._obter_raiz_repositorio_git()
            if not repositorio:
                self.sinal_git_finalizado.emit(
                    False, "A pasta do aplicativo não pertence a um repositório Git existente."
                )
                return

            os.makedirs(PASTA_CHECKLISTS, exist_ok=True)
            pasta_relativa = os.path.relpath(PASTA_CHECKLISTS, repositorio)
            planilha_relativa = os.path.relpath(self.dados.arquivo, repositorio)

            subprocess.run(
                ["git", "-C", repositorio, "add", "--", f"{pasta_relativa}/.", planilha_relativa],
                check=True, capture_output=True, text=True, timeout=15
            )

            msg_commit = f"Sincronização manual - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            res_commit = subprocess.run(
                ["git", "-C", repositorio, "commit", "-m", msg_commit, "--", f"{pasta_relativa}/.", planilha_relativa],
                capture_output=True, text=True, timeout=15
            )

            res_push = subprocess.run(
                ["git", "-C", repositorio, "push"],
                capture_output=True, text=True, timeout=30
            )

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

    def _executar_git(self, diretorio, argumentos, timeout=10):
        return subprocess.run(
            ["git", "-C", diretorio] + list(argumentos),
            capture_output=True, text=True, timeout=timeout
        )

    def _obter_raiz_repositorio_git(self):
        resultado = self._executar_git(
            PASTA_APLICACAO, ["rev-parse", "--show-toplevel"], timeout=5
        )
        if resultado.returncode != 0:
            return None
        raiz = resultado.stdout.strip()
        return os.path.realpath(raiz) if raiz else None

    def publicar_pdf_no_github(self, pdf_path):
        """Publica apenas este PDF no branch GitHub já configurado; nunca cria/clona repositório."""
        pdf_path = os.path.realpath(os.path.abspath(pdf_path))
        if not pdf_path.lower().endswith(".pdf") or not os.path.isfile(pdf_path):
            return False, "PDF não encontrado ou extensão inválida. O arquivo local foi preservado."

        with self.git_lock:
            repositorio = self._obter_raiz_repositorio_git()
            if not repositorio:
                return False, "Repositório Git existente não encontrado; o PDF ficou salvo localmente."

            try:
                if os.path.commonpath([repositorio, pdf_path]) != repositorio:
                    return False, "PDF está fora do repositório existente; nada foi enviado."
            except ValueError:
                return False, "Caminho do PDF inválido; nada foi enviado."

            caminho_relativo = os.path.relpath(pdf_path, repositorio)

            ignorado = self._executar_git(
                repositorio, ["check-ignore", "-q", "--", caminho_relativo], timeout=5
            )
            if ignorado.returncode == 0:
                return False, "A pasta/arquivo está no .gitignore; PDF preservado localmente."
            if ignorado.returncode not in (1,):
                return False, "Não foi possível verificar as regras .gitignore; nada foi enviado."

            branch_result = self._executar_git(
                repositorio, ["symbolic-ref", "--quiet", "--short", "HEAD"], timeout=5
            )
            if branch_result.returncode != 0:
                return False, "HEAD está destacado; configure uma branch local antes do envio."
            branch = branch_result.stdout.strip()

            remote_result = self._executar_git(
                repositorio, ["config", "--get", f"branch.{branch}.remote"], timeout=5
            )
            merge_result = self._executar_git(
                repositorio, ["config", "--get", f"branch.{branch}.merge"], timeout=5
            )
            if remote_result.returncode != 0 or merge_result.returncode != 0:
                return False, "A branch não tem remoto de publicação configurado; PDF ficou local."

            remoto = remote_result.stdout.strip()
            ref_remota = merge_result.stdout.strip()
            if remoto == "." or not ref_remota.startswith("refs/heads/"):
                return False, "A branch não aponta para uma branch remota publicável."

            url_result = self._executar_git(
                repositorio, ["remote", "get-url", remoto], timeout=5
            )
            if url_result.returncode != 0 or "github.com" not in url_result.stdout.lower():
                return False, "Não encontrei um remoto GitHub configurado para esta branch."

            branch_remota = ref_remota[len("refs/heads/"):]
            ref_tracking = f"refs/remotes/{remoto}/{branch_remota}"
            fetch = self._executar_git(
                repositorio,
                ["fetch", "--quiet", remoto, f"{ref_remota}:{ref_tracking}"],
                timeout=25
            )
            if fetch.returncode != 0:
                return False, "Falha ao consultar o GitHub. Verifique rede/permissões; PDF ficou local."

            divergencia = self._executar_git(
                repositorio,
                ["rev-list", "--left-right", "--count", f"HEAD...{ref_tracking}"],
                timeout=5
            )
            if divergencia.returncode != 0:
                return False, "Não foi possível comparar a branch local com o GitHub; nada foi enviado."
            contagens = divergencia.stdout.strip().split()
            if len(contagens) != 2 or contagens != ["0", "0"]:
                return False, "Branch local/remota divergente ou com commits pendentes; sincronize manualmente. PDF ficou local."

            adicionar = self._executar_git(
                repositorio, ["add", "--", caminho_relativo], timeout=10
            )
            if adicionar.returncode != 0:
                return False, "Git não conseguiu adicionar o PDF; arquivo preservado localmente."

            diferenca = self._executar_git(
                repositorio, ["diff", "--cached", "--quiet", "--", caminho_relativo], timeout=5
            )
            if diferenca.returncode == 1:
                commit = self._executar_git(
                    repositorio,
                    ["commit", "-m", f"Adicionar checklist PDF: {os.path.basename(pdf_path)}", "--", caminho_relativo],
                    timeout=15
                )
                if commit.returncode != 0:
                    return False, "Falha ao criar commit. Configure user.name/user.email; PDF ficou local."
            elif diferenca.returncode != 0:
                return False, "Falha ao verificar o PDF preparado para commit; nada foi enviado."

            push = self._executar_git(
                repositorio, ["push", remoto, f"HEAD:{ref_remota}"], timeout=35
            )
            if push.returncode != 0:
                return False, "GitHub recusou/não concluiu o envio. Confira rede e credenciais; PDF ficou local."

            return True, f"PDF enviado ao GitHub: {os.path.basename(pdf_path)}"

    @pyqtSlot(bool, str)
    def ao_concluir_publicacao_pdf(self, sucesso, mensagem):
        cor = "#1B5E20" if sucesso else "#B71C1C"
        for nome_label in ("lbl_status_pdf_aprovado", "lbl_status_pdf_reprovado"):
            label = getattr(self, nome_label, None)
            if label is not None:
                label.setText(mensagem)
                label.setStyleSheet(f"color: {cor}; font-size: 9pt; font-weight: bold;")
        print(f"[GITHUB PDF] {'OK' if sucesso else 'FALHA'}: {mensagem}")

    @pyqtSlot(bool, str)
    def ao_concluir_sincronizacao_git(self, sucesso, mensagem):
        self.container_btn_rede.setEnabled(True)

        if sucesso:
            self.lbl_status_rede_detalhe.setText(f"SINCRONIZAÇÃO CONCLUÍDA!\n\n{mensagem}")
            self.lbl_status_rede_detalhe.setStyleSheet(
                "color: #1B5E20; padding: 15px; border: 2px solid #2E7D32; border-radius: 10px; background-color: #E8F5E9;"
            )
            QTimer.singleShot(4000, lambda: self.mudar_tela(self.tela_menu_mestre_principal, "MENU_MESTRE_PRINCIPAL"))
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
        btn_cancelar.clicked.connect(self.cancelar_leitura_rfid)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl_instrucao)
        layout.addWidget(self.lbl_status, alignment=Qt.AlignCenter)
        layout.addWidget(btn_cancelar, alignment=Qt.AlignCenter)

        tela.setLayout(layout)
        return tela

    def preparar_leitura(self, estado, instrucao, origem_voltar="TELA_PRINCIPAL"):
        self.origem_voltar_leitura = origem_voltar
        self.lbl_instrucao.setText(instrucao)
        self.lbl_status.setText("Aguardando leitura do leitor RFID...")
        self.lbl_status.setStyleSheet(
            "color: #424242; padding: 20px; border: 2px dashed #BDBDBD; border-radius: 12px; background-color: #FFFFFF;"
        )
        self.mudar_tela(self.tela_leitura, estado)

    def cancelar_leitura_rfid(self):
        if self.origem_voltar_leitura == "SELECAO_NIVEL":
            self.mudar_tela(self.tela_selecao_nivel_habilitar, "SELECAO_NIVEL")
        elif self.origem_voltar_leitura == "MENU_MESTRE_NIVEL2":
            self.mudar_tela(self.tela_menu_mestre_nivel2, "MENU_MESTRE_NIVEL2")
        elif self.origem_voltar_leitura == "MENU_MESTRE_PRINCIPAL":
            self.mudar_tela(self.tela_menu_mestre_principal, "MENU_MESTRE_PRINCIPAL")
        else:
            self.mudar_tela(self.tela_liberar_gt, "TELA_PRINCIPAL")

    def mostrar_mensagem(self, texto, cor_fundo, cor_texto):
        self.lbl_status.setText(texto)
        self.lbl_status.setStyleSheet(
            f"color: {cor_texto}; padding: 15px; border: 2px solid {cor_fundo}; border-radius: 12px; background-color: {cor_fundo}; font-weight: bold;"
        )
        QTimer.singleShot(3000, self.cancelar_leitura_rfid)

    # ========================================================================
    # CHECKLIST (AMPLIADO E OTIMIZADO PARA TOUCHSCREEN 800x480)
    # ========================================================================
    def criar_bloco_pergunta(self, idx_pergunta):
        container = QtWidgets.QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 2px solid #CFD8DC;
                border-radius: 12px;
            }
        """)
        container.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        lbl_p = QtWidgets.QLabel(f"{idx_pergunta + 1}. {self.perguntas[idx_pergunta]}")
        lbl_p.setFont(QFont("Arial", 17, QFont.Bold))
        lbl_p.setWordWrap(True)
        lbl_p.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lbl_p.setStyleSheet("background-color: transparent; color: #000000; border: none; padding: 2px;")

        h_btn = QtWidgets.QHBoxLayout()
        h_btn.setSpacing(20)
        h_btn.setAlignment(Qt.AlignCenter)

        btn_ok = QtWidgets.QPushButton("OK")
        btn_ok.setFont(QFont("Arial", 16, QFont.Bold))
        btn_ok.setFixedSize(220, 48)
        btn_ok.setStyleSheet(
            "background-color: #E8F5E9; color: #1B5E20; border: 2px solid #2E7D32; border-radius: 8px; font-weight: bold; font-size: 16pt;"
        )

        btn_nok = QtWidgets.QPushButton("NÃO OK")
        btn_nok.setFont(QFont("Arial", 16, QFont.Bold))
        btn_nok.setFixedSize(220, 48)
        btn_nok.setStyleSheet(
            "background-color: #FFEBEE; color: #B71C1C; border: 2px solid #C62828; border-radius: 8px; font-weight: bold; font-size: 16pt;"
        )

        btn_ok.clicked.connect(lambda: self.selecionar_resposta(idx_pergunta, "OK", btn_ok, btn_nok))
        btn_nok.clicked.connect(lambda: self.selecionar_resposta(idx_pergunta, "NÃO OK", btn_ok, btn_nok))

        h_btn.addWidget(btn_ok)
        h_btn.addWidget(btn_nok)

        layout.addWidget(lbl_p, 1)
        layout.addLayout(h_btn)
        return container

    def selecionar_resposta(self, idx, valor, btn_ok, btn_nok):
        self.respostas_checklist[idx] = valor
        if valor == "OK":
            btn_ok.setStyleSheet(
                "background-color: #2E7D32; color: white; border: 2px solid #1B5E20; border-radius: 8px; font-weight: bold; font-size: 16pt;"
            )
            btn_nok.setStyleSheet(
                "background-color: #FFEBEE; color: #B71C1C; border: 2px solid #C62828; border-radius: 8px; font-weight: bold; font-size: 16pt;"
            )
        else:
            btn_nok.setStyleSheet(
                "background-color: #C62828; color: white; border: 2px solid #8E0000; border-radius: 8px; font-weight: bold; font-size: 16pt;"
            )
            btn_ok.setStyleSheet(
                "background-color: #E8F5E9; color: #1B5E20; border: 2px solid #2E7D32; border-radius: 8px; font-weight: bold; font-size: 16pt;"
            )

    def criar_tela_par_perguntas(self, idx1, idx2):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tela)
        layout.setContentsMargins(10, 4, 10, 6)
        layout.setSpacing(6)

        lbl_hdr = self.criar_widget_cabecalho()

        header = QtWidgets.QLabel("CHECKLIST DE SEGURANÇA")
        header.setFont(QFont("Arial", 13, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #1A237E; background-color: transparent; margin: 0px; padding: 0px;")

        bloco1 = self.criar_bloco_pergunta(idx1)
        bloco2 = self.criar_bloco_pergunta(idx2)

        botoes_nav = QtWidgets.QHBoxLayout()
        botoes_nav.setSpacing(14)

        style_btn_nav = """
            QPushButton {{
                background-color: {cor};
                color: white;
                border-radius: 8px;
                font-weight: bold;
                font-size: 15pt;
            }}
            QPushButton:pressed {{
                background-color: {cor_press};
            }}
        """

        btn_voltar = QtWidgets.QPushButton("◄ ANTERIOR")
        btn_voltar.setFixedHeight(48)
        btn_voltar.setStyleSheet(style_btn_nav.format(cor="#757575", cor_press="#424242"))

        idx_tela_atual = idx1 // 2
        if idx_tela_atual == 0:
            btn_voltar.clicked.connect(lambda: self.mudar_tela(self.tela_liberar_gt, "TELA_PRINCIPAL"))
        else:
            btn_voltar.clicked.connect(lambda: self.mudar_tela(self.telas_checklist_perguntas[idx_tela_atual - 1],
                                                               f"CHK_PAG_{idx_tela_atual - 1}"))

        btn_proximo = QtWidgets.QPushButton("PRÓXIMO ►")
        btn_proximo.setFixedHeight(48)
        btn_proximo.setStyleSheet(style_btn_nav.format(cor="#1565C0", cor_press="#0D47A1"))
        btn_proximo.clicked.connect(lambda: self.validar_e_avancar_pagina(idx_tela_atual))

        botoes_nav.addWidget(btn_voltar)
        botoes_nav.addWidget(btn_proximo)

        layout.addWidget(lbl_hdr)
        layout.addWidget(header)
        layout.addWidget(bloco1, 1)
        layout.addWidget(bloco2, 1)
        layout.addLayout(botoes_nav)
        return tela

    def criar_tela_pergunta_final(self, idx_pergunta):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tela)
        layout.setContentsMargins(10, 4, 10, 6)
        layout.setSpacing(6)

        lbl_hdr = self.criar_widget_cabecalho()

        header = QtWidgets.QLabel("CHECKLIST DE SEGURANÇA - FINALIZAÇÃO")
        header.setFont(QFont("Arial", 13, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #1A237E; background-color: transparent; margin: 0px; padding: 0px;")

        bloco1 = self.criar_bloco_pergunta(idx_pergunta)

        botoes_nav = QtWidgets.QHBoxLayout()
        botoes_nav.setSpacing(14)

        style_btn_nav = """
            QPushButton {{
                background-color: {cor};
                color: white;
                border-radius: 8px;
                font-weight: bold;
                font-size: 15pt;
            }}
            QPushButton:pressed {{
                background-color: {cor_press};
            }}
        """

        btn_voltar = QtWidgets.QPushButton("◄ ANTERIOR")
        btn_voltar.setFixedHeight(48)
        btn_voltar.setStyleSheet(style_btn_nav.format(cor="#757575", cor_press="#424242"))
        btn_voltar.clicked.connect(lambda: self.mudar_tela(self.telas_checklist_perguntas[4], "CHK_PAG_4"))

        btn_concluir = QtWidgets.QPushButton("CONCLUIR CHECKLIST")
        self.btn_concluir_checklist = btn_concluir
        btn_concluir.setFixedHeight(48)
        btn_concluir.setStyleSheet(style_btn_nav.format(cor="#2E7D32", cor_press="#1B5E20"))
        btn_concluir.clicked.connect(self.processar_finalizacao_checklist)

        botoes_nav.addWidget(btn_voltar)
        botoes_nav.addWidget(btn_concluir)

        layout.addWidget(lbl_hdr)
        layout.addWidget(header)
        layout.addWidget(bloco1, 1)
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

        self.lbl_status_pdf_aprovado = QtWidgets.QLabel("Gerando PDF e enviando ao GitHub...")
        self.lbl_status_pdf_aprovado.setAlignment(Qt.AlignCenter)
        self.lbl_status_pdf_aprovado.setWordWrap(True)
        self.lbl_status_pdf_aprovado.setStyleSheet("color: #616161; font-size: 9pt;")

        # REQUISITO 6: Botão Voltar ao Menu Principal mantém GPIOs e Cronômetro rodando
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
        btn_voltar_menu.clicked.connect(self.voltar_ao_menu_principal_sem_desligar)

        layout.addWidget(lbl_titulo, alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl_msg_aprovado, alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl_tempo_restante, alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl_status_pdf_aprovado, alignment=Qt.AlignCenter)
        layout.addWidget(btn_voltar_menu, alignment=Qt.AlignCenter)

        return widget

    def voltar_ao_menu_principal_sem_desligar(self):
        """Retorna à tela principal mantendo o cronômetro e os GPIOs acionados (Requisito 6)."""
        self.mudar_tela(self.tela_liberar_gt, "TELA_PRINCIPAL")

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

        self.lbl_status_pdf_reprovado = QtWidgets.QLabel("Gerando PDF e enviando ao GitHub...")
        self.lbl_status_pdf_reprovado.setAlignment(Qt.AlignCenter)
        self.lbl_status_pdf_reprovado.setWordWrap(True)
        self.lbl_status_pdf_reprovado.setStyleSheet("color: #FFFFFF; font-size: 9pt; font-weight: bold;")

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(lbl_msg)
        layout.addWidget(lbl_trava)
        layout.addWidget(self.lbl_status_pdf_reprovado)
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
        QTimer.singleShot(3000, self.cancelar_leitura_rfid)

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
                        "background-color: #E8F5E9; color: #1B5E20; border: 2px solid #2E7D32; border-radius: 8px; font-weight: bold; font-size: 16pt;"
                    )
                elif btn.text() == "NÃO OK":
                    btn.setStyleSheet(
                        "background-color: #FFEBEE; color: #B71C1C; border: 2px solid #C62828; border-radius: 8px; font-weight: bold; font-size: 16pt;"
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
            self.mudar_tela(self.tela_liberar_gt, "TELA_PRINCIPAL")
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
        for nome_label in ("lbl_status_pdf_aprovado", "lbl_status_pdf_reprovado"):
            label = getattr(self, nome_label, None)
            if label is not None:
                label.setText("Gerando PDF e enviando ao GitHub...")
                label.setStyleSheet("color: #616161; font-size: 9pt; font-weight: bold;")

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
                sucesso, mensagem = self.publicar_pdf_no_github(pdf_path)
                self.sinal_pdf_publicado.emit(sucesso, mensagem)
            else:
                self.sinal_pdf_publicado.emit(
                    False, "Falha ao gerar o PDF; confira o log. O checklist não foi enviado."
                )
        except Exception as erro:
            print(f"[CHECKLIST] Erro ao gerar registro PDF: {erro}")
            self.sinal_pdf_publicado.emit(
                False, "Erro ao gerar/publicar o PDF; confira o log."
            )

    def liberar_equipamento_por_3min(self, matricula, nome):
        self.timer_liberacao.stop()
        self.timer_cronometro.stop()
        set_gpios(1)
        self.fim_liberacao = time.monotonic() + self.tempo_liberacao_segundos
        self.lbl_msg_aprovado.setText(f"Checklist Aprovado:\n[{matricula}] {nome}")
        self.mudar_tela(self.tela_aprovado, "EQUIPAMENTO_LIBERADO")
        self.atualizar_cronometro_liberacao()
        self.timer_cronometro.start(1000)
        self.timer_liberacao.start(self.tempo_liberacao_segundos * 1000)

    def finalizar_tempo_liberacao(self):
        self.timer_liberacao.stop()
        self.timer_cronometro.stop()
        self.fim_liberacao = None
        self.finalizacao_em_andamento = False

        if hasattr(self, 'btn_concluir_checklist'):
            self.btn_concluir_checklist.setEnabled(True)

        if hasattr(self, 'lbl_tempo_restante'):
            self.lbl_tempo_restante.setText("00:00:00")

        if hasattr(self, 'lbl_status_main'):
            self.lbl_status_main.setText("Aguardando leitura do crachá...")
            self.lbl_status_main.setStyleSheet(
                "color: #424242; padding: 20px; border: 2px dashed #BDBDBD; border-radius: 12px; background-color: #FFFFFF;"
            )

        set_gpios(0)
        if self.central_widget.currentWidget() in [self.tela_aprovado]:
            self.mudar_tela(self.tela_liberar_gt, "TELA_PRINCIPAL")

    # ========================================================================
    # PROCESSAMENTO DE LEITURA RFID E NÍVEIS DE USUÁRIO (REQUISITOS 1 A 6)
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
            func = self.dados.buscar_por_cracha(uid_clean) if uid_clean != UID_MESTRE else None
            is_mestre = (uid_clean == UID_MESTRE) or (func and func.get('status') in ['M2', 'MESTRE'])
            if is_mestre:
                print("✓ Sistema desbloqueado com Crachá Mestre!")
                self.mudar_tela(self.tela_liberar_gt, "TELA_PRINCIPAL")
            return

        # ====================================================================
        # PROCESSAMENTO NA TELA PRINCIPAL
        # ====================================================================
        if self.estado_atual == "TELA_PRINCIPAL":
            # REQUISITO 3: MESTRE PRINCIPAL
            if uid_clean == UID_MESTRE:
                print("✓ Mestre Principal autenticado. Abrindo Menu Administrativo...")
                self.mudar_tela(self.tela_menu_mestre_principal, "MENU_MESTRE_PRINCIPAL")
                return

            func = self.dados.buscar_por_cracha(uid_clean)
            if not func:
                self.mostrar_mensagem_main("ACESSO NEGADO\n\nCrachá não cadastrado!", "#C62828", "white", 3)
                return

            status = func.get('status', 'D')
            if status == 'D':
                self.mostrar_mensagem_main(f"ACESSO NEGADO\n\nUsuário Desabilitado!\n{func['nome']}", "#C62828", "white", 3)
                return

            # REQUISITO 5: MESTRE NÍVEL 2
            if status == 'M2':
                print(f"✓ Mestre Nível 2 autenticado: {func['nome']}. Abrindo Menu Mestre Nível 2...")
                self.mestre_n2_atual = func
                self.mudar_tela(self.tela_menu_mestre_nivel2, "MENU_MESTRE_NIVEL2")
                return

            # REQUISITO 2: USUÁRIO COMUM
            # REQUISITO 6: Se o equipamento já está liberado
            if self.fim_liberacao is not None:
                self.mostrar_mensagem_main(
                    "Equipamento já está acionado.\nAguarde o cronômetro acabar.",
                    "#E65100",
                    "white",
                    3
                )
                return

            # Usuário Comum com equipamento desligado
            turno_atual = self.obter_turno_atual()
            aprovados_no_turno = self.checklists_aprovados_turno.get(turno_atual, set())

            if func['matricula'] in aprovados_no_turno:
                self.liberar_equipamento_por_3min(func['matricula'], func['nome'])
            else:
                self.iniciar_checklist_para_usuario(func)
            return

        # ====================================================================
        # PROCESSAMENTO DE CADASTRO / HABILITAÇÃO NA TELA DE LEITURA
        # ====================================================================
        if self.central_widget.currentWidget() != self.tela_leitura:
            return

        if self.estado_atual == "HABILITAR_USUARIO_COMUM":
            func = self.dados.buscar_por_cracha(uid_clean)
            if func:
                if self.dados.alterar_status(uid_clean, 'H'):
                    self.mostrar_confirmacao_operacao("USUÁRIO COMUM HABILITADO", "#2E7D32")
                else:
                    self.mostrar_mensagem("ERRO\n\nFalha ao atualizar planilha!", "#C62828", "white")
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não encontrado na planilha!", "#C62828", "white")

        elif self.estado_atual == "HABILITAR_USUARIO_COMUM_N2":
            func = self.dados.buscar_por_cracha(uid_clean)
            if func:
                if self.dados.alterar_status(uid_clean, 'H'):
                    self.mostrar_confirmacao_operacao("USUÁRIO COMUM HABILITADO", "#2E7D32")
                else:
                    self.mostrar_mensagem("ERRO\n\nFalha ao atualizar planilha!", "#C62828", "white")
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não encontrado na planilha!", "#C62828", "white")

        elif self.estado_atual == "HABILITAR_MESTRE_N2":
            func = self.dados.buscar_por_cracha(uid_clean)
            if func:
                if self.dados.alterar_status(uid_clean, 'M2'):
                    self.mostrar_confirmacao_operacao("MESTRE NÍVEL 2 HABILITADO", "#2E7D32")
                else:
                    self.mostrar_mensagem("ERRO\n\nFalha ao atualizar planilha!", "#C62828", "white")
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não encontrado na planilha!", "#C62828", "white")

        elif self.estado_atual == "DESABILITAR_USUARIO":
            func = self.dados.buscar_por_cracha(uid_clean)
            if func:
                if self.dados.alterar_status(uid_clean, 'D'):
                    self.mostrar_confirmacao_operacao("USUÁRIO DESABILITADO", "#C62828")
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
            operador_seguro = re.sub(r"[^A-Za-z0-9_-]+", "_", str(dados.get("operador", "operador"))).strip("_") or "operador"
            nome_arq = f"checklist_{operador_seguro}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.pdf"
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
