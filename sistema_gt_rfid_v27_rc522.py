#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema Completo de Controle de Acesso GBMX - Liberar GT
Otimizado para Tela Raspberry Pi de 5 Polegadas (800x480)
"""

import sys
import os
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
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QFont
from PyQt5.QtCore import pyqtSignal, QObject, Qt, QTimer

# ============================================================================
# CONFIGURAÇÕES E GPIO
# ============================================================================
UID_MESTRE = "3293600699"

REPO_URL = "https://AutomationGBMX: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@github.com/AutomationGBMX/checklists-gt.git"
REPO_LOCAL = "./checklists-repo"
PASTA_CHECKLISTS = "./checklists"

# Inicialização de Hardware GPIO
try:
    import RPi.GPIO as GPIO

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(23, GPIO.OUT, initial=GPIO.LOW)  # LED Verde
    GPIO.setup(24, GPIO.OUT, initial=GPIO.LOW)  # Relé Liberar GT
    HAS_GPIO = True
except Exception as e:
    print(f"[AVISO] RPi.GPIO não inicializado (Execução fora da Raspberry Pi): {e}")
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


# ============================================================================
# EMISSOR DE SINAIS E THREAD RFID (RC522)
# ============================================================================
class RFIDSignals(QObject):
    uid_recebido = pyqtSignal(str)


class LeituraRC522(threading.Thread):
    def __init__(self):
        super().__init__()
        self.signals = RFIDSignals()
        self.ativo = True
        self.daemon = True

    def run(self):
        try:
            from mfrc522 import SimpleMFRC522
            reader = SimpleMFRC522()
            print("✓ Leitor RC522 inicializado com sucesso!")

            while self.ativo:
                try:
                    id_card = reader.read_id()
                    if id_card:
                        try:
                            num_bytes = (id_card.bit_length() + 7) // 8
                            if num_bytes < 4:
                                num_bytes = 4
                            uid_bytes = id_card.to_bytes(num_bytes, byteorder='big')
                            uid_le = int.from_bytes(uid_bytes[:4], byteorder='little')
                            uid = str(uid_le)
                        except Exception:
                            uid = str(id_card)
                        print(f"[RFID] UID Lido: {uid}")
                        self.signals.uid_recebido.emit(uid)
                        time.sleep(0.8)
                except Exception:
                    time.sleep(0.2)
        except Exception as e:
            print(f"✗ Erro no módulo RC522: {e}")

    def parar(self):
        self.ativo = False


# ============================================================================
# GERENCIAMENTO DE DADOS (EXCEL)
# ============================================================================
class GerenciadorDados:
    def __init__(self, arquivo_excel='Lista_Basedecrachás.xlsx'):
        self.arquivo = arquivo_excel
        self.df = None
        self.carregar_planilha()

    def carregar_planilha(self):
        try:
            if os.path.exists(self.arquivo):
                self.df = pd.read_excel(self.arquivo)
                if 'STATUS' not in self.df.columns:
                    self.df['STATUS'] = 'D'
                    self.salvar_planilha()
                print(f"✓ Base de dados carregada: {len(self.df)} registros")
                return True
            return False
        except Exception as e:
            print(f"✗ Erro ao carregar planilha: {e}")
            return False

    def salvar_planilha(self):
        try:
            if self.df is not None:
                self.df.to_excel(self.arquivo, index=False)
                return True
        except Exception:
            return False

    def buscar_por_cracha(self, uid):
        if self.df is None: return None
        try:
            uid_int = int(uid)
            resultado = self.df[self.df['CRACHÁ'] == uid_int]
            if not resultado.empty:
                linha = resultado.iloc[0]
                return {
                    'nome': str(linha['NOME']),
                    'matricula': str(int(linha['MATRICULA'])),
                    'cracha': str(int(linha['CRACHÁ'])),
                    'status': str(linha.get('STATUS', 'D'))
                }
            return None
        except Exception:
            return None

    def alterar_status(self, uid, novo_status):
        if self.df is None: return False
        try:
            uid_int = int(uid)
            idx = self.df.index[self.df['CRACHÁ'] == uid_int].tolist()
            if idx:
                self.df.at[idx[0], 'STATUS'] = novo_status
                self.salvar_planilha()
                return True
            return False
        except Exception:
            return False


# ============================================================================
# GERENCIADOR GITHUB
# ============================================================================
class GerenciadorGitHub:
    def __init__(self):
        self.repo_url = REPO_URL
        self.inicializar_repo()

    def inicializar_repo(self):
        try:
            if not os.path.exists(REPO_LOCAL):
                subprocess.run(f"git clone {REPO_URL} {REPO_LOCAL}", shell=True, capture_output=True, timeout=60)
        except Exception as e:
            print(f"[GIT] Erro ao inicializar repo: {e}")

    def fazer_upload_pdf(self, arquivo_pdf):
        try:
            if not os.path.exists(arquivo_pdf): return False
            arquivo_abs = os.path.abspath(arquivo_pdf)
            nome_arquivo = os.path.basename(arquivo_pdf)
            repo_abs = os.path.abspath(REPO_LOCAL)

            import shutil
            if os.path.exists(repo_abs):
                shutil.rmtree(repo_abs)

            res_clone = subprocess.run(f"git clone {self.repo_url} {repo_abs}", shell=True, capture_output=True,
                                       timeout=60)
            if res_clone.returncode != 0: return False

            pasta_repo = os.path.join(repo_abs, 'checklists')
            os.makedirs(pasta_repo, exist_ok=True)
            destino = os.path.join(pasta_repo, nome_arquivo)

            with open(arquivo_abs, 'rb') as f_in, open(destino, 'wb') as f_out:
                f_out.write(f_in.read())

            subprocess.run(f'git -C {repo_abs} config user.email "checklist@gbmx.com"', shell=True, capture_output=True,
                           timeout=10)
            subprocess.run(f'git -C {repo_abs} config user.name "Sistema GBMX"', shell=True, capture_output=True,
                           timeout=10)
            subprocess.run(f"git -C {repo_abs} add .", shell=True, capture_output=True, timeout=30)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            subprocess.run(f'git -C {repo_abs} commit -m "Checklist {timestamp}"', shell=True, capture_output=True,
                           timeout=30)

            branch = subprocess.run(f"git -C {repo_abs} rev-parse --abbrev-ref HEAD", shell=True, capture_output=True,
                                    text=True, timeout=10)
            b_name = branch.stdout.strip() if branch.returncode == 0 else "main"

            res_push = subprocess.run(f"git -C {repo_abs} push origin {b_name}", shell=True, capture_output=True,
                                      timeout=60)
            return res_push.returncode == 0
        except Exception as e:
            print(f"[GIT] Erro de upload: {e}")
            return False


# ============================================================================
# JANELA PRINCIPAL DO SISTEMA GT
# ============================================================================
class SistemaGT(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.dados = GerenciadorDados()
        self.git = GerenciadorGitHub()

        # Lista de Rótulos de Cabeçalho (Data, Hora e Turno)
        self.labels_data_hora = []

        # Gerenciamento de Turnos e Checklists Aprovados
        self.checklists_aprovados_turno = {}

        # Dados da Sessão Atual
        self.operador_atual = None
        self.respostas_checklist = {}

        # Thread RFID
        self.serial = LeituraRC522()
        self.serial.signals.uid_recebido.connect(self.processar_rfid)
        self.serial.start()

        # Timer para Liberação Temporizada (3 minutos)
        self.timer_liberacao = QTimer(self)
        self.timer_liberacao.setSingleShot(True)
        self.timer_liberacao.timeout.connect(self.finalizar_tempo_liberacao)

        # Timer de Relógio Digital
        self.timer_relogio = QTimer(self)
        self.timer_relogio.timeout.connect(self.atualizar_relogio)
        self.timer_relogio.start(1000)

        # Perguntas Fixas
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
        print(f"[SISTEMA] Checklists do turno {turno_atual} foram invalidados.")

    def criar_widget_cabecalho(self):
        lbl = QtWidgets.QLabel()
        lbl.setFont(QFont("Arial", 13, QFont.Bold))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #1A237E; background-color: #E8EAF6; padding: 5px 14px; border-radius: 6px;")
        self.labels_data_hora.append(lbl)
        return lbl

    def atualizar_relogio(self):
        texto = f"{datetime.now().strftime('%d/%m/%Y - %H:%M:%S')}  |  {self.obter_texto_turno_atual()}"
        for lbl in self.labels_data_hora:
            lbl.setText(texto)

    def configurar_interface(self):
        self.setWindowTitle("SISTEMA GBMX - LIBERAR GT")
        self.setStyleSheet("background-color: #f4f4f9;")

        self.setFixedSize(800, 480)
        self.showFullScreen()

        self.central_widget = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.central_widget)

        # Construção das Telas
        self.tela_liberar_gt = self.criar_tela_menu_liberar_gt()
        self.tela_leitura = self.criar_tela_leitura()

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

        # Adicionar Telas ao Stacked Widget
        self.central_widget.addWidget(self.tela_liberar_gt)
        self.central_widget.addWidget(self.tela_leitura)
        for t in self.telas_checklist_perguntas:
            self.central_widget.addWidget(t)
        self.central_widget.addWidget(self.tela_aprovado)
        self.central_widget.addWidget(self.tela_reprovado_bloqueado)

        self.central_widget.setCurrentWidget(self.tela_liberar_gt)
        self.estado_atual = "MENU_GT"

    def mudar_tela(self, tela, novo_estado):
        self.estado_atual = novo_estado
        self.central_widget.setCurrentWidget(tela)

    # ========================================================================
    # TELA INICIAL: MENU - LIBERAR GT
    # ========================================================================
    def criar_tela_menu_liberar_gt(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(12)

        lbl_hdr = self.criar_widget_cabecalho()

        titulo = QtWidgets.QLabel("MENU - LIBERAR GT")
        titulo.setFont(QFont("Arial", 20, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("color: #212121; margin-top: 2px; margin-bottom: 5px;")

        btn_liberar = QtWidgets.QPushButton("1 - LIBERAR EQUIPAMENTO")
        btn_liberar.setFont(QFont("Arial", 14, QFont.Bold))
        btn_liberar.setFixedSize(460, 55)
        btn_liberar.setStyleSheet("background-color: #2E7D32; color: white; border-radius: 8px;")
        btn_liberar.clicked.connect(
            lambda: self.preparar_leitura("LIBERAR_EQUIPAMENTO", "Aproxime o crachá para LIBERAR O EQUIPAMENTO"))

        btn_habilitar = QtWidgets.QPushButton("2 - HABILITAR USUÁRIO")
        btn_habilitar.setFont(QFont("Arial", 14, QFont.Bold))
        btn_habilitar.setFixedSize(460, 55)
        btn_habilitar.setStyleSheet("background-color: #1565C0; color: white; border-radius: 8px;")
        btn_habilitar.clicked.connect(
            lambda: self.preparar_leitura("HABILITAR_USUARIO_MESTRE", "Aproxime o CRACHÁ MESTRE para autorizar"))

        btn_desabilitar = QtWidgets.QPushButton("3 - DESABILITAR USUÁRIO")
        btn_desabilitar.setFont(QFont("Arial", 14, QFont.Bold))
        btn_desabilitar.setFixedSize(460, 55)
        btn_desabilitar.setStyleSheet("background-color: #C62828; color: white; border-radius: 8px;")
        btn_desabilitar.clicked.connect(
            lambda: self.preparar_leitura("DESABILITAR_USUARIO_MESTRE", "Aproxime o CRACHÁ MESTRE para autorizar"))

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(titulo, alignment=Qt.AlignCenter)
        layout.addWidget(btn_liberar, alignment=Qt.AlignCenter)
        layout.addWidget(btn_habilitar, alignment=Qt.AlignCenter)
        layout.addWidget(btn_desabilitar, alignment=Qt.AlignCenter)

        tela.setLayout(layout)
        return tela

    # ========================================================================
    # TELA DE LEITURA RFID
    # ========================================================================
    def criar_tela_leitura(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(15, 10, 15, 10)

        lbl_hdr = self.criar_widget_cabecalho()

        self.lbl_instrucao = QtWidgets.QLabel("Aproxime o seu crachá...")
        self.lbl_instrucao.setFont(QFont("Arial", 16, QFont.Bold))
        self.lbl_instrucao.setAlignment(Qt.AlignCenter)
        self.lbl_instrucao.setStyleSheet("color: #333; margin-top: 10px; margin-bottom: 15px;")

        self.lbl_status = QtWidgets.QLabel("Aguardando leitura do leitor RFID...")
        self.lbl_status.setFont(QFont("Arial", 13))
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet(
            "color: #555; padding: 20px; border: 2px dashed #BDBDBD; border-radius: 10px; background-color: #FFFFFF;")
        self.lbl_status.setFixedSize(550, 140)

        btn_cancelar = QtWidgets.QPushButton("CANCELAR")
        btn_cancelar.setFont(QFont("Arial", 14, QFont.Bold))
        btn_cancelar.setFixedSize(220, 48)
        btn_cancelar.setStyleSheet("background-color: #757575; color: white; border-radius: 6px; margin-top: 15px;")
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
            "color: #555; padding: 20px; border: 2px dashed #BDBDBD; border-radius: 10px; background-color: #FFFFFF;")
        self.mudar_tela(self.tela_leitura, estado)

    def mostrar_mensagem(self, texto, cor_fundo, cor_texto):
        self.lbl_status.setText(texto)
        self.lbl_status.setStyleSheet(
            f"color: {cor_texto}; padding: 15px; border: 2px solid {cor_fundo}; border-radius: 10px; background-color: {cor_fundo}; font-weight: bold;")
        QTimer.singleShot(2500, lambda: self.mudar_tela(self.tela_liberar_gt, "MENU_GT"))

    # ========================================================================
    # CONSTRUTOR DE TELAS DE CHECKLIST (FONTE AUMENTADA)
    # ========================================================================
    def criar_bloco_pergunta(self, idx_pergunta):
        container = QtWidgets.QGroupBox(f"Item {idx_pergunta + 1}")
        container.setStyleSheet(
            "QGroupBox { font-size: 13px; font-weight: bold; color: #1565C0; border: 1px solid #BBDEFB; border-radius: 6px; margin-top: 4px; background-color: #FFFFFF; }")

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        # FONTE DAS PERGUNTAS AUMENTADA PARA 14pt BOLD
        lbl_p = QtWidgets.QLabel(self.perguntas[idx_pergunta])
        lbl_p.setFont(QFont("Arial", 14, QFont.Bold))
        lbl_p.setWordWrap(True)
        lbl_p.setStyleSheet("color: #212121;")

        h_btn = QtWidgets.QHBoxLayout()
        h_btn.setSpacing(15)

        btn_ok = QtWidgets.QPushButton("OK")
        btn_ok.setFont(QFont("Arial", 13, QFont.Bold))
        btn_ok.setFixedHeight(42)
        btn_ok.setStyleSheet(
            "background-color: #E8F5E9; color: #2E7D32; border: 2px solid #2E7D32; border-radius: 6px;")

        btn_nok = QtWidgets.QPushButton("NÃO OK")
        btn_nok.setFont(QFont("Arial", 13, QFont.Bold))
        btn_nok.setFixedHeight(42)
        btn_nok.setStyleSheet(
            "background-color: #FFEBEE; color: #C62828; border: 2px solid #C62828; border-radius: 6px;")

        btn_ok.clicked.connect(lambda: self.selecionar_resposta(idx_pergunta, "OK", btn_ok, btn_nok))
        btn_nok.clicked.connect(lambda: self.selecionar_resposta(idx_pergunta, "NÃO OK", btn_ok, btn_nok))

        h_btn.addWidget(btn_ok)
        h_btn.addWidget(btn_nok)

        layout.addWidget(lbl_p)
        layout.addLayout(h_btn)
        container.setLayout(layout)
        return container

    def selecionar_resposta(self, idx, valor, btn_ok, btn_nok):
        self.respostas_checklist[idx] = valor
        if valor == "OK":
            btn_ok.setStyleSheet(
                "background-color: #2E7D32; color: white; border: 2px solid #2E7D32; border-radius: 6px;")
            btn_nok.setStyleSheet(
                "background-color: #FFEBEE; color: #C62828; border: 2px solid #C62828; border-radius: 6px;")
        else:
            btn_nok.setStyleSheet(
                "background-color: #C62828; color: white; border: 2px solid #C62828; border-radius: 6px;")
            btn_ok.setStyleSheet(
                "background-color: #E8F5E9; color: #2E7D32; border: 2px solid #2E7D32; border-radius: 6px;")

    def criar_tela_par_perguntas(self, idx1, idx2):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(4)

        lbl_hdr = self.criar_widget_cabecalho()

        header = QtWidgets.QLabel("CHECKLIST DE SEGURANÇA - GUINCHO TRACIONADOR")
        header.setFont(QFont("Arial", 12, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #1A237E;")

        bloco1 = self.criar_bloco_pergunta(idx1)
        bloco2 = self.criar_bloco_pergunta(idx2)

        botoes_nav = QtWidgets.QHBoxLayout()

        btn_voltar = QtWidgets.QPushButton("◄ ANTERIOR")
        btn_voltar.setFont(QFont("Arial", 12, QFont.Bold))
        btn_voltar.setFixedHeight(45)
        btn_voltar.setStyleSheet("background-color: #757575; color: white; border-radius: 6px;")

        idx_tela_atual = idx1 // 2
        if idx_tela_atual == 0:
            btn_voltar.clicked.connect(lambda: self.mudar_tela(self.tela_liberar_gt, "MENU_GT"))
        else:
            btn_voltar.clicked.connect(lambda: self.mudar_tela(self.telas_checklist_perguntas[idx_tela_atual - 1],
                                                               f"CHK_PAG_{idx_tela_atual - 1}"))

        btn_proximo = QtWidgets.QPushButton("PRÓXIMO ►")
        btn_proximo.setFont(QFont("Arial", 12, QFont.Bold))
        btn_proximo.setFixedHeight(45)
        btn_proximo.setStyleSheet("background-color: #1565C0; color: white; border-radius: 6px;")
        btn_proximo.clicked.connect(lambda: self.validar_e_avancar_pagina(idx_tela_atual))

        botoes_nav.addWidget(btn_voltar)
        botoes_nav.addWidget(btn_proximo)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(header)
        layout.addWidget(bloco1)
        layout.addWidget(bloco2)
        layout.addLayout(botoes_nav)

        tela.setLayout(layout)
        return tela

    def criar_tela_pergunta_final(self, idx_pergunta):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(6)

        lbl_hdr = self.criar_widget_cabecalho()

        header = QtWidgets.QLabel("CHECKLIST DE SEGURANÇA - FINALIZAÇÃO")
        header.setFont(QFont("Arial", 12, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #1A237E;")

        bloco1 = self.criar_bloco_pergunta(idx_pergunta)

        botoes_nav = QtWidgets.QHBoxLayout()
        btn_voltar = QtWidgets.QPushButton("◄ ANTERIOR")
        btn_voltar.setFont(QFont("Arial", 12, QFont.Bold))
        btn_voltar.setFixedHeight(45)
        btn_voltar.setStyleSheet("background-color: #757575; color: white; border-radius: 6px;")
        btn_voltar.clicked.connect(lambda: self.mudar_tela(self.telas_checklist_perguntas[4], "CHK_PAG_4"))

        btn_concluir = QtWidgets.QPushButton("CONCLUIR CHECKLIST")
        btn_concluir.setFont(QFont("Arial", 12, QFont.Bold))
        btn_concluir.setFixedHeight(45)
        btn_concluir.setStyleSheet("background-color: #2E7D32; color: white; border-radius: 6px;")
        btn_concluir.clicked.connect(self.processar_finalizacao_checklist)

        botoes_nav.addWidget(btn_voltar)
        botoes_nav.addWidget(btn_concluir)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(header)
        layout.addWidget(bloco1)
        layout.addStretch()
        layout.addLayout(botoes_nav)

        tela.setLayout(layout)
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
        tela = QtWidgets.QWidget()
        tela.setStyleSheet("background-color: #2E7D32;")

        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)

        lbl_hdr = self.criar_widget_cabecalho()

        self.lbl_msg_aprovado = QtWidgets.QLabel("Checklist Aprovado")
        self.lbl_msg_aprovado.setFont(QFont("Arial", 20, QFont.Bold))
        self.lbl_msg_aprovado.setStyleSheet("color: white;")
        self.lbl_msg_aprovado.setAlignment(Qt.AlignCenter)

        lbl_sub = QtWidgets.QLabel("EQUIPAMENTO LIBERADO POR 3 MINUTOS")
        lbl_sub.setFont(QFont("Arial", 16, QFont.Bold))
        lbl_sub.setStyleSheet("color: #E8F5E9;")
        lbl_sub.setAlignment(Qt.AlignCenter)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(self.lbl_msg_aprovado)
        layout.addWidget(lbl_sub)
        tela.setLayout(layout)
        return tela

    def criar_tela_reprovado_bloqueado(self):
        tela = QtWidgets.QWidget()
        tela.setStyleSheet("background-color: #C62828;")

        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)

        lbl_hdr = self.criar_widget_cabecalho()

        lbl_msg = QtWidgets.QLabel("Checklist Reprovado\nContate a Segurança / Manutenção")
        lbl_msg.setFont(QFont("Arial", 18, QFont.Bold))
        lbl_msg.setStyleSheet("color: white;")
        lbl_msg.setAlignment(Qt.AlignCenter)

        lbl_trava = QtWidgets.QLabel("SISTEMA BLOQUEADO\nAproxime o Crachá Mestre para desbloquear")
        lbl_trava.setFont(QFont("Arial", 14, QFont.Bold))
        lbl_trava.setStyleSheet("color: #FFEBEE;")
        lbl_trava.setAlignment(Qt.AlignCenter)

        layout.addWidget(lbl_hdr, alignment=Qt.AlignCenter)
        layout.addWidget(lbl_msg)
        layout.addWidget(lbl_trava)
        tela.setLayout(layout)
        return tela

    # ========================================================================
    # PROCESSAMENTO DE CHECKLIST E LIBERAÇÃO
    # ========================================================================
    def iniciar_checklist_para_usuario(self, func_dados):
        self.operador_atual = func_dados
        self.respostas_checklist.clear()

        for tela in self.telas_checklist_perguntas:
            for groupbox in tela.findChildren(QtWidgets.QGroupBox):
                for btn in groupbox.findChildren(QtWidgets.QPushButton):
                    if btn.text() == "OK":
                        btn.setStyleSheet(
                            "background-color: #E8F5E9; color: #2E7D32; border: 2px solid #2E7D32; border-radius: 6px;")
                    elif btn.text() == "NÃO OK":
                        btn.setStyleSheet(
                            "background-color: #FFEBEE; color: #C62828; border: 2px solid #C62828; border-radius: 6px;")

        self.mudar_tela(self.telas_checklist_perguntas[0], "CHK_PAG_0")

    def processar_finalizacao_checklist(self):
        if len(self.respostas_checklist) != len(self.perguntas):
            QtWidgets.QMessageBox.warning(self, "Atenção", "Responda a todas as perguntas.")
            return

        respostas_lista = [self.respostas_checklist[i] for i in range(len(self.perguntas))]
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

        pdf_path = self.gerar_pdf_checklist(dados_checklist)
        if pdf_path:
            threading.Thread(target=self.git.fazer_upload_pdf, args=(pdf_path,), daemon=True).start()

        if not reprovado:
            turno_atual = self.obter_turno_atual()
            if turno_atual not in self.checklists_aprovados_turno:
                self.checklists_aprovados_turno[turno_atual] = set()
            self.checklists_aprovados_turno[turno_atual].add(self.operador_atual['matricula'])

            self.liberar_equipamento_por_3min(self.operador_atual['matricula'], self.operador_atual['nome'])
        else:
            self.invalidar_checklists_do_turno()
            self.mudar_tela(self.tela_reprovado_bloqueado, "SISTEMA_BLOQUEADO")

    def liberar_equipamento_por_3min(self, matricula, nome):
        set_gpios(1)
        self.lbl_msg_aprovado.setText(f"Checklist Aprovado:\n[{matricula}] {nome}")
        self.mudar_tela(self.tela_aprovado, "EQUIPAMENTO_LIBERADO")
        self.timer_liberacao.start(180000)

    def finalizar_tempo_liberacao(self):
        set_gpios(0)
        self.mudar_tela(self.tela_liberar_gt, "MENU_GT")

    # ========================================================================
    # PROCESSAMENTO DE LEITURA RFID
    # ========================================================================
    def processar_rfid(self, uid):
        print(f"[PROCESSAR RFID] UID: {uid} | Estado: {self.estado_atual}")

        if self.estado_atual == "SISTEMA_BLOQUEADO":
            if uid == UID_MESTRE:
                print("✓ Sistema desbloqueado com Crachá Mestre!")
                self.mudar_tela(self.tela_liberar_gt, "MENU_GT")
            return

        if self.central_widget.currentWidget() != self.tela_leitura:
            return

        if self.estado_atual == "LIBERAR_EQUIPAMENTO":
            func = self.dados.buscar_por_cracha(uid)
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
            if uid == UID_MESTRE:
                self.estado_atual = "HABILITAR_USUARIO_FINAL"
                self.lbl_instrucao.setText("Aproxime o crachá do USUÁRIO")
                self.lbl_status.setText("Mestre Autorizado!\nAguardando crachá do Usuário...")
                self.lbl_status.setStyleSheet(
                    "color: #2E7D32; padding: 15px; border: 2px solid #2E7D32; border-radius: 10px; font-weight: bold;")
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não é Mestre!", "#C62828", "white")

        elif self.estado_atual == "HABILITAR_USUARIO_FINAL":
            func = self.dados.buscar_por_cracha(uid)
            if func:
                if self.dados.alterar_status(uid, 'H'):
                    self.mostrar_mensagem(f"SUCESSO\n\nUsuário HABILITADO!\n{func['nome']}", "#2E7D32", "white")
                else:
                    self.mostrar_mensagem("ERRO\n\nFalha ao atualizar base!", "#C62828", "white")
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não encontrado!", "#C62828", "white")

        elif self.estado_atual == "DESABILITAR_USUARIO_MESTRE":
            if uid == UID_MESTRE:
                self.estado_atual = "DESABILITAR_USUARIO_FINAL"
                self.lbl_instrucao.setText("Aproxime o crachá do USUÁRIO")
                self.lbl_status.setText("Mestre Autorizado!\nAguardando crachá do Usuário...")
                self.lbl_status.setStyleSheet(
                    "color: #2E7D32; padding: 15px; border: 2px solid #2E7D32; border-radius: 10px; font-weight: bold;")
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não é Mestre!", "#C62828", "white")

        elif self.estado_atual == "DESABILITAR_USUARIO_FINAL":
            func = self.dados.buscar_por_cracha(uid)
            if func:
                if self.dados.alterar_status(uid, 'D'):
                    self.mostrar_mensagem(f"SUCESSO\n\nUsuário DESABILITADO!\n{func['nome']}", "#EF6C00", "white")
                else:
                    self.mostrar_mensagem("ERRO\n\nFalha ao atualizar base!", "#C62828", "white")
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

    def closeEvent(self, event):
        set_gpios(0)
        self.serial.parar()
        event.accept()


# ============================================================================
# EXECUÇÃO DA APLICAÇÃO
# ============================================================================
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = SistemaGT()
    window.show()
    sys.exit(app.exec_())