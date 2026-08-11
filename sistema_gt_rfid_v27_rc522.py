#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema Completo de Controle de Acesso GBMX
Atualizado em 11/08/2026
Integração com Leitor RFID, Planilha Excel, Controle de Equipamento e Checklist com Email e PDF
"""

import sys
import os
# import serial (removido)
import threading
import time
import subprocess
import pandas as pd
from datetime import datetime

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtCore import pyqtSignal, QObject, Qt, QTimer


# Configurações
UID_MESTRE = "3293600699"

# GitHub Configuration
REPO_URL = "https://AutomationGBMX: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@github.com/AutomationGBMX/checklists-gt.git"
REPO_LOCAL = "./checklists-repo"
PASTA_CHECKLISTS = "./checklists"



# ============================================================================
# CLASSE PARA EMITIR SINAIS DE THREAD
# ============================================================================
class RFIDSignals(QObject):
    uid_recebido = pyqtSignal(str)

# ============================================================================
# CLASSE PARA COMUNICAÇÃO SERIAL (RFID + ESP32)
# ============================================================================
class LeituraRC522(threading.Thread):
    def __init__(self):
        super().__init__()
        self.signals = RFIDSignals()
        self.ativo = True
        self.daemon = True
        self.reader = None
        
    def run(self):
        try:
            import RPi.GPIO as GPIO
            from mfrc522 import SimpleMFRC522
            
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            print("Inicializando RC522...")
            self.reader = SimpleMFRC522()
            print("✓ RC522 conectado com sucesso!")
            
            while self.ativo:
                try:
                    id_card = self.reader.read_id()
                    if id_card:
                        # Converter Big Endian para Little Endian (como na planilha)
                        try:
                            num_bytes = (id_card.bit_length() + 7) // 8
                            if num_bytes < 4:
                                num_bytes = 4
                            uid_bytes = id_card.to_bytes(num_bytes, byteorder='big')
                            uid_le = int.from_bytes(uid_bytes[:4], byteorder='little')
                            uid = str(uid_le)
                        except Exception:
                            uid = str(id_card)
                        print(f"[RFID] UID Recebido (LE): {uid}")
                        self.signals.uid_recebido.emit(uid)
                        time.sleep(0.5)
                except Exception as e:
                    pass
                    
        except Exception as e:
            print(f"✗ Erro na leitura RC522: {e}")
        finally:
            try:
                import RPi.GPIO as GPIO
                GPIO.cleanup()
            except:
                pass
    
    def parar(self):
        self.ativo = False

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
                print(f"✓ Planilha carregada: {len(self.df)} registros")
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
        except Exception as e:
            return False
    
    def buscar_por_cracha(self, uid):
        if self.df is None: return None
        try:
            uid_int = int(uid)
            resultado = self.df[self.df['CRACHÁ'] == uid_int]
            
            if not resultado.empty:
                linha = resultado.iloc[0]
                status = str(linha.get('STATUS', 'D'))
                return {
                    'nome': str(linha['NOME']),
                    'matricula': str(int(linha['MATRICULA'])),
                    'cracha': str(int(linha['CRACHÁ'])),
                    'status': status
                }
            return None
        except Exception as e:
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
        except Exception as e:
            return False

# ============================================================================
# CLASSE PARA GERENCIAR GITHUB
# ============================================================================
class GerenciadorGitHub:
    def __init__(self):
        self.repo_url = REPO_URL
        self.inicializar_repo()
    
    def inicializar_repo(self):
        try:
            if not os.path.exists(REPO_LOCAL):
                print("[GIT] Clonando repositorio...")
                resultado = subprocess.run(
                    f"git clone {REPO_URL} {REPO_LOCAL}",
                    shell=True, capture_output=True, text=True, timeout=60
                )
                if resultado.returncode == 0:
                    print("[GIT] Repositorio clonado")
                else:
                    print(f"[GIT] Erro: {resultado.stderr}")
            else:
                print("[GIT] Repositorio ja existe")
        except Exception as e:
            print(f"[GIT] Erro: {e}")
    
    def fazer_upload_pdf(self, arquivo_pdf):
        try:
            if not os.path.exists(arquivo_pdf):
                print(f"[GIT] Arquivo nao encontrado: {arquivo_pdf}")
                return False
            
            arquivo_abs = os.path.abspath(arquivo_pdf)
            nome_arquivo = os.path.basename(arquivo_pdf)
            repo_abs = os.path.abspath(REPO_LOCAL)
            
            # Apagar repo local e clonar novamente para garantir sincronia
            print(f"[GIT] Atualizando repositorio local...")
            import shutil
            if os.path.exists(repo_abs):
                shutil.rmtree(repo_abs)
            
            resultado_clone = subprocess.run(
                f"git clone {self.repo_url} {repo_abs}",
                shell=True, capture_output=True, text=True, timeout=60
            )
            if resultado_clone.returncode != 0:
                print(f"[GIT] Erro no clone: {resultado_clone.stderr}")
                return False
            
            # Copiar PDF para a pasta checklists/ dentro do repo
            pasta_checklists_repo = os.path.join(repo_abs, 'checklists')
            os.makedirs(pasta_checklists_repo, exist_ok=True)
            destino = os.path.join(pasta_checklists_repo, nome_arquivo)
            print(f"[GIT] Copiando {nome_arquivo} para checklists/...")
            with open(arquivo_abs, 'rb') as f:
                conteudo = f.read()
            with open(destino, 'wb') as f:
                f.write(conteudo)
            
            # Configurar identidade git (necessario para commit)
            subprocess.run(f'git -C {repo_abs} config user.email "checklist@gbmx.com"', shell=True, capture_output=True, timeout=10)
            subprocess.run(f'git -C {repo_abs} config user.name "Sistema GBMX"', shell=True, capture_output=True, timeout=10)
            
            # Commit e push
            subprocess.run(f"git -C {repo_abs} add .", shell=True, capture_output=True, timeout=30)
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            msg = f"Checklist adicionado em {timestamp}"
            r_commit = subprocess.run(f'git -C {repo_abs} commit -m "{msg}"', shell=True, capture_output=True, text=True, timeout=30)
            print(f"[GIT] Commit: {r_commit.stdout.strip() or r_commit.stderr.strip()}")
            
            # Detectar branch
            branch = subprocess.run(f"git -C {repo_abs} rev-parse --abbrev-ref HEAD", shell=True, capture_output=True, text=True, timeout=10)
            branch_name = branch.stdout.strip() if branch.returncode == 0 else "main"
            
            resultado = subprocess.run(f"git -C {repo_abs} push origin {branch_name}", shell=True, capture_output=True, text=True, timeout=60)
            
            if resultado.returncode == 0:
                print(f"[GIT] Upload realizado com sucesso: {nome_arquivo}")
                return True
            else:
                print(f"[GIT] Erro no push: {resultado.stderr}")
                return False
            
        except Exception as e:
            print(f"[GIT] Erro no upload: {e}")
            return False

# ============================================================================
# JANELA PRINCIPAL DO SISTEMA
# ============================================================================
class SistemaGT(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.dados = GerenciadorDados()
        self.git = GerenciadorGitHub()
        self.serial = LeituraRC522()
        self.serial.signals.uid_recebido.connect(self.processar_rfid)
        self.serial.start()
        
        self.estado_atual = "TELA_INICIAL"
        self.respostas_checklist = {}  # Armazenar respostas
        self.radios_ok = []  # Botões SIM
        self.radios_nok = []  # Botões NÃO
        self.txt_obs = QtWidgets.QTextEdit()  # Inicializar aqui
        
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
        
    def mudar_tela(self, tela, novo_estado):
        self.estado_atual = novo_estado
        self.central_widget.setCurrentWidget(tela)
    
    def preparar_leitura(self, estado, instrucao):
        self.lbl_instrucao.setText(instrucao)
        self.lbl_status.setText("Aguardando leitura...")
        self.lbl_status.setStyleSheet("color: #666; padding: 20px; border: 2px dashed #ccc; border-radius: 10px; background-color: #fff;")
        self.mudar_tela(self.tela_leitura, estado)
        
    def mostrar_mensagem(self, texto, cor_fundo, cor_texto):
        self.lbl_status.setText(texto)
        self.lbl_status.setStyleSheet(f"color: {cor_texto}; padding: 20px; border: 2px solid {cor_fundo}; border-radius: 10px; background-color: {cor_fundo};")
        QTimer.singleShot(3000, lambda: self.mudar_tela(self.tela_liberar_gt, "MENU_GT"))
        
    def configurar_interface(self):
        self.setWindowTitle("SISTEMA GBMX - CONTROLE DE ACESSO")
        self.setStyleSheet("background-color: #f0f0f0;")
        # Fullscreen ajustado à tela
        screen = QtWidgets.QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        self.setGeometry(screen_geometry)
        self.showFullScreen()
        
        self.central_widget = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.central_widget)
        
        self.tela_inicial = self.criar_tela_inicial()
        self.tela_liberar_gt = self.criar_tela_liberar_gt()
        self.tela_leitura = self.criar_tela_leitura()
        self.tela_checklist_credenciais = self.criar_tela_checklist_credenciais()
        self.tela_checklist_perguntas_1 = self.criar_tela_checklist_perguntas_1()
        self.tela_checklist_perguntas_2 = self.criar_tela_checklist_perguntas_2()
        self.tela_checklist_perguntas_3 = self.criar_tela_checklist_perguntas_3()
        self.tela_checklist_perguntas_4 = self.criar_tela_checklist_perguntas_4()
        self.tela_checklist_perguntas_5 = self.criar_tela_checklist_perguntas_5()
        self.tela_checklist_perguntas_6 = self.criar_tela_checklist_perguntas_6()
        
        self.central_widget.addWidget(self.tela_inicial)
        self.central_widget.addWidget(self.tela_liberar_gt)
        self.central_widget.addWidget(self.tela_leitura)
        self.central_widget.addWidget(self.tela_checklist_credenciais)
        self.central_widget.addWidget(self.tela_checklist_perguntas_1)
        self.central_widget.addWidget(self.tela_checklist_perguntas_2)
        self.central_widget.addWidget(self.tela_checklist_perguntas_3)
        self.central_widget.addWidget(self.tela_checklist_perguntas_4)
        self.central_widget.addWidget(self.tela_checklist_perguntas_5)
        self.central_widget.addWidget(self.tela_checklist_perguntas_6)
        
        self.central_widget.setCurrentWidget(self.tela_inicial)

    # ========================================================================
    # TELA INICIAL
    # ========================================================================
    def criar_tela_inicial(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        
        titulo = QtWidgets.QLabel("SISTEMA DE GESTÃO GBMX")
        titulo.setFont(QFont("Arial", 28, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("color: #333; margin-bottom: 40px;")
        
        btn_liberar = QtWidgets.QPushButton("LIBERAR GT")
        btn_liberar.setFont(QFont("Arial", 20, QFont.Bold))
        btn_liberar.setFixedSize(450, 100)
        btn_liberar.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 10px;")
        btn_liberar.clicked.connect(lambda: self.mudar_tela(self.tela_liberar_gt, "MENU_GT"))
        
        btn_checklist = QtWidgets.QPushButton("CHECKLIST DE SEGURANÇA")
        btn_checklist.setFont(QFont("Arial", 20, QFont.Bold))
        btn_checklist.setFixedSize(450, 100)
        btn_checklist.setStyleSheet("background-color: #2196F3; color: white; border-radius: 10px; margin-top: 20px;")
        btn_checklist.clicked.connect(lambda: self.iniciar_checklist())
        
        layout.addWidget(titulo)
        layout.addWidget(btn_liberar, alignment=Qt.AlignCenter)
        layout.addWidget(btn_checklist, alignment=Qt.AlignCenter)
        
        tela.setLayout(layout)
        return tela

    # ========================================================================
    # TELA MENU LIBERAR GT
    # ========================================================================
    def criar_tela_liberar_gt(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        
        titulo = QtWidgets.QLabel("MENU - LIBERAR GT")
        titulo.setFont(QFont("Arial", 24, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("color: #333; margin-bottom: 30px;")
        
        btn_liberar = QtWidgets.QPushButton("1 - LIBERAR EQUIPAMENTO")
        btn_liberar.setFont(QFont("Arial", 18, QFont.Bold))
        btn_liberar.setFixedSize(450, 70)
        btn_liberar.setStyleSheet("background-color: #FF9800; color: white; border-radius: 5px; margin-bottom: 15px;")
        btn_liberar.clicked.connect(lambda: self.preparar_leitura("LIBERAR_EQUIPAMENTO", "Aproxime seu crachá para liberar o equipamento"))
        
        btn_habilitar = QtWidgets.QPushButton("2 - HABILITAR USUÁRIO")
        btn_habilitar.setFont(QFont("Arial", 18, QFont.Bold))
        btn_habilitar.setFixedSize(450, 70)
        btn_habilitar.setStyleSheet("background-color: #8BC34A; color: white; border-radius: 5px; margin-bottom: 15px;")
        btn_habilitar.clicked.connect(lambda: self.preparar_leitura("HABILITAR_USUARIO_MESTRE", "Aproxime o CRACHÁ MESTRE para autorizar"))
        
        btn_desabilitar = QtWidgets.QPushButton("3 - DESABILITAR USUÁRIO")
        btn_desabilitar.setFont(QFont("Arial", 18, QFont.Bold))
        btn_desabilitar.setFixedSize(450, 70)
        btn_desabilitar.setStyleSheet("background-color: #F44336; color: white; border-radius: 5px; margin-bottom: 30px;")
        btn_desabilitar.clicked.connect(lambda: self.preparar_leitura("DESABILITAR_USUARIO_MESTRE", "Aproxime o CRACHÁ MESTRE para autorizar"))
        
        btn_voltar = QtWidgets.QPushButton("← VOLTAR")
        btn_voltar.setFont(QFont("Arial", 16, QFont.Bold))
        btn_voltar.setFixedSize(250, 60)
        btn_voltar.setStyleSheet("background-color: #9E9E9E; color: white; border-radius: 5px;")
        btn_voltar.clicked.connect(lambda: self.mudar_tela(self.tela_inicial, "TELA_INICIAL"))
        
        layout.addWidget(titulo)
        layout.addWidget(btn_liberar, alignment=Qt.AlignCenter)
        layout.addWidget(btn_habilitar, alignment=Qt.AlignCenter)
        layout.addWidget(btn_desabilitar, alignment=Qt.AlignCenter)
        layout.addWidget(btn_voltar, alignment=Qt.AlignCenter)
        
        tela.setLayout(layout)
        return tela

    # ========================================================================
    # TELA DE LEITURA RFID
    # ========================================================================
    def criar_tela_leitura(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        
        self.lbl_instrucao = QtWidgets.QLabel("Aproxime o crachá...")
        self.lbl_instrucao.setFont(QFont("Arial", 26, QFont.Bold))
        self.lbl_instrucao.setAlignment(Qt.AlignCenter)
        self.lbl_instrucao.setStyleSheet("color: #333; margin-bottom: 40px;")
        
        self.lbl_status = QtWidgets.QLabel("Aguardando leitura...")
        self.lbl_status.setFont(QFont("Arial", 18))
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color: #666; padding: 30px; border: 2px dashed #ccc; border-radius: 10px; background-color: #fff;")
        self.lbl_status.setMinimumWidth(700)
        self.lbl_status.setMinimumHeight(200)
        
        btn_cancelar = QtWidgets.QPushButton("CANCELAR")
        btn_cancelar.setFont(QFont("Arial", 16, QFont.Bold))
        btn_cancelar.setFixedSize(250, 60)
        btn_cancelar.setStyleSheet("background-color: #F44336; color: white; border-radius: 5px; margin-top: 40px;")
        btn_cancelar.clicked.connect(lambda: self.mudar_tela(self.tela_liberar_gt, "MENU_GT"))
        
        layout.addWidget(self.lbl_instrucao)
        layout.addWidget(self.lbl_status, alignment=Qt.AlignCenter)
        layout.addWidget(btn_cancelar, alignment=Qt.AlignCenter)
        
        tela.setLayout(layout)
        return tela

    # ========================================================================
    # TELA CHECKLIST - CREDENCIAIS
    # ========================================================================
    def criar_tela_checklist_credenciais(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(10)
        
        titulo = QtWidgets.QLabel("CHECKLIST DE SEGURANÇA - EQUIPAMENTO 1172")
        titulo.setFont(QFont("Arial", 18, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("color: #333; margin-bottom: 10px;")
        
        self.lbl_status_chk = QtWidgets.QLabel("Aproxime seu crachá para preencher seus dados.")
        self.lbl_status_chk.setStyleSheet("color: #E65100; font-weight: bold; padding: 8px; font-size: 14px;")
        self.lbl_status_chk.setAlignment(Qt.AlignCenter)
        
        # Formulário com labels e campos lado a lado
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)
        
        lbl_nome = QtWidgets.QLabel("Operador / Nome:")
        lbl_nome.setFont(QFont("Arial", 14, QFont.Bold))
        self.input_operador = QtWidgets.QLineEdit()
        self.input_operador.setReadOnly(True)
        self.input_operador.setStyleSheet("background-color: #e0e0e0; padding: 8px; font-size: 14px;")
        self.input_operador.setMinimumHeight(40)
        
        lbl_mat = QtWidgets.QLabel("Matrícula:")
        lbl_mat.setFont(QFont("Arial", 14, QFont.Bold))
        self.input_matricula = QtWidgets.QLineEdit()
        self.input_matricula.setReadOnly(True)
        self.input_matricula.setStyleSheet("background-color: #e0e0e0; padding: 8px; font-size: 14px;")
        self.input_matricula.setMinimumHeight(40)
        
        lbl_equip = QtWidgets.QLabel("Nº Equipamento:")
        lbl_equip.setFont(QFont("Arial", 14, QFont.Bold))
        self.input_equipamento = QtWidgets.QLineEdit("1172")
        self.input_equipamento.setReadOnly(True)
        self.input_equipamento.setStyleSheet("background-color: #e0e0e0; padding: 8px; font-size: 14px;")
        self.input_equipamento.setMinimumHeight(40)
        
        grid.addWidget(lbl_nome, 0, 0)
        grid.addWidget(self.input_operador, 0, 1)
        grid.addWidget(lbl_mat, 1, 0)
        grid.addWidget(self.input_matricula, 1, 1)
        grid.addWidget(lbl_equip, 2, 0)
        grid.addWidget(self.input_equipamento, 2, 1)
        
        # Botões
        botoes_layout = QtWidgets.QHBoxLayout()
        botoes_layout.setSpacing(15)
        
        btn_voltar = QtWidgets.QPushButton("CANCELAR")
        btn_voltar.setStyleSheet("background-color: #F44336; color: #333; padding: 12px; font-weight: bold; font-size: 16px;")
        btn_voltar.setMinimumHeight(55)
        btn_voltar.clicked.connect(self.cancelar_checklist)
        
        self.btn_proximo_chk = QtWidgets.QPushButton("PRÓXIMO →")
        self.btn_proximo_chk.setStyleSheet("background-color: #4CAF50; color: #333; padding: 12px; font-weight: bold; font-size: 16px;")
        self.btn_proximo_chk.setMinimumHeight(55)
        self.btn_proximo_chk.setEnabled(False)
        self.btn_proximo_chk.clicked.connect(lambda: self.mudar_tela(self.tela_checklist_perguntas_1, "CHECKLIST_PERGUNTAS_1"))
        
        botoes_layout.addWidget(btn_voltar)
        botoes_layout.addWidget(self.btn_proximo_chk)
        
        layout.addWidget(titulo)
        layout.addWidget(self.lbl_status_chk)
        layout.addLayout(grid)
        layout.addStretch()
        layout.addLayout(botoes_layout)
        
        tela.setLayout(layout)
        return tela

    # ========================================================================
    # TELA CHECKLIST - PERGUNTAS 1-2
    # ========================================================================
    def criar_tela_checklist_perguntas_1(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # Pergunta 1
        lbl_p1 = QtWidgets.QLabel(f"1. {self.perguntas[0]}")
        lbl_p1.setWordWrap(True)
        lbl_p1.setStyleSheet("font-size: 15px; font-weight: bold; padding: 5px; color: #333;")
        
        h_layout_1 = QtWidgets.QHBoxLayout()
        h_layout_1.setSpacing(10)
        
        btn_sim_1 = QtWidgets.QPushButton("✓ SIM")
        btn_sim_1.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
        btn_sim_1.setMinimumHeight(50)
        btn_sim_1.clicked.connect(lambda: self.marcar_resposta(0, "OK", btn_sim_1, btn_nao_1))
        
        btn_nao_1 = QtWidgets.QPushButton("✗ NÃO")
        btn_nao_1.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
        btn_nao_1.setMinimumHeight(50)
        btn_nao_1.clicked.connect(lambda: self.marcar_resposta(0, "NÃO OK", btn_sim_1, btn_nao_1))
        
        self.radios_ok.append(btn_sim_1)
        self.radios_nok.append(btn_nao_1)
        
        h_layout_1.addWidget(btn_sim_1)
        h_layout_1.addWidget(btn_nao_1)
        
        layout.addWidget(lbl_p1)
        layout.addLayout(h_layout_1)
        
        # Separador
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)
        
        # Pergunta 2
        lbl_p2 = QtWidgets.QLabel(f"2. {self.perguntas[1]}")
        lbl_p2.setWordWrap(True)
        lbl_p2.setStyleSheet("font-size: 15px; font-weight: bold; padding: 5px; color: #333;")
        
        h_layout_2 = QtWidgets.QHBoxLayout()
        h_layout_2.setSpacing(10)
        
        btn_sim_2 = QtWidgets.QPushButton("✓ SIM")
        btn_sim_2.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
        btn_sim_2.setMinimumHeight(50)
        btn_sim_2.clicked.connect(lambda: self.marcar_resposta(1, "OK", btn_sim_2, btn_nao_2))
        
        btn_nao_2 = QtWidgets.QPushButton("✗ NÃO")
        btn_nao_2.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
        btn_nao_2.setMinimumHeight(50)
        btn_nao_2.clicked.connect(lambda: self.marcar_resposta(1, "NÃO OK", btn_sim_2, btn_nao_2))
        
        self.radios_ok.append(btn_sim_2)
        self.radios_nok.append(btn_nao_2)
        
        h_layout_2.addWidget(btn_sim_2)
        h_layout_2.addWidget(btn_nao_2)
        
        layout.addWidget(lbl_p2)
        layout.addLayout(h_layout_2)
        
        layout.addStretch()
        
        # Botões de navegação
        botoes_layout = QtWidgets.QHBoxLayout()
        botoes_layout.setSpacing(10)
        
        btn_anterior = QtWidgets.QPushButton("◀ ANTERIOR")
        btn_anterior.setStyleSheet("background-color: #ccc; color: #666; font-weight: bold; font-size: 13px; padding: 8px; border-radius: 5px;")
        btn_anterior.setMinimumHeight(50)
        btn_anterior.clicked.connect(lambda: self.mudar_tela(self.tela_checklist_perguntas_1, "CHECKLIST_PERGUNTAS_1"))
        
        btn_proximo = QtWidgets.QPushButton("PRÓXIMO ▶")
        btn_proximo.setStyleSheet("background-color: #ccc; color: #666; font-weight: bold; font-size: 13px; padding: 8px; border-radius: 5px;")
        btn_proximo.setMinimumHeight(50)
        btn_proximo.clicked.connect(lambda: self.mudar_tela(self.tela_checklist_perguntas_2, "CHECKLIST_PERGUNTAS_2"))
        
        botoes_layout.addWidget(btn_anterior)
        botoes_layout.addWidget(btn_proximo)
        
        layout.addLayout(botoes_layout)
        
        tela.setLayout(layout)
        return tela

    # ========================================================================
    # TELA CHECKLIST - PERGUNTAS 3-4
    # ========================================================================
    def criar_tela_checklist_perguntas_2(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # Pergunta 3
        lbl_p3 = QtWidgets.QLabel(f"3. {self.perguntas[2]}")
        lbl_p3.setWordWrap(True)
        lbl_p3.setStyleSheet("font-size: 15px; font-weight: bold; padding: 5px; color: #333;")
        
        h_layout_3 = QtWidgets.QHBoxLayout()
        h_layout_3.setSpacing(10)
        
        btn_sim_3 = QtWidgets.QPushButton("✓ SIM")
        btn_sim_3.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
        btn_sim_3.setMinimumHeight(50)
        btn_sim_3.clicked.connect(lambda: self.marcar_resposta(2, "OK", btn_sim_3, btn_nao_3))
        
        btn_nao_3 = QtWidgets.QPushButton("✗ NÃO")
        btn_nao_3.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
        btn_nao_3.setMinimumHeight(50)
        btn_nao_3.clicked.connect(lambda: self.marcar_resposta(2, "NÃO OK", btn_sim_3, btn_nao_3))
        
        self.radios_ok.append(btn_sim_3)
        self.radios_nok.append(btn_nao_3)
        
        h_layout_3.addWidget(btn_sim_3)
        h_layout_3.addWidget(btn_nao_3)
        
        layout.addWidget(lbl_p3)
        layout.addLayout(h_layout_3)
        
        # Separador
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)
        
        # Pergunta 4
        lbl_p4 = QtWidgets.QLabel(f"4. {self.perguntas[3]}")
        lbl_p4.setWordWrap(True)
        lbl_p4.setStyleSheet("font-size: 15px; font-weight: bold; padding: 5px; color: #333;")
        
        h_layout_4 = QtWidgets.QHBoxLayout()
        h_layout_4.setSpacing(10)
        
        btn_sim_4 = QtWidgets.QPushButton("✓ SIM")
        btn_sim_4.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
        btn_sim_4.setMinimumHeight(50)
        btn_sim_4.clicked.connect(lambda: self.marcar_resposta(3, "OK", btn_sim_4, btn_nao_4))
        
        btn_nao_4 = QtWidgets.QPushButton("✗ NÃO")
        btn_nao_4.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
        btn_nao_4.setMinimumHeight(50)
        btn_nao_4.clicked.connect(lambda: self.marcar_resposta(3, "NÃO OK", btn_sim_4, btn_nao_4))
        
        self.radios_ok.append(btn_sim_4)
        self.radios_nok.append(btn_nao_4)
        
        h_layout_4.addWidget(btn_sim_4)
        h_layout_4.addWidget(btn_nao_4)
        
        layout.addWidget(lbl_p4)
        layout.addLayout(h_layout_4)
        
        layout.addStretch()
        
        # Botões de navegação
        botoes_layout = QtWidgets.QHBoxLayout()
        botoes_layout.setSpacing(10)
        
        btn_anterior = QtWidgets.QPushButton("◀ ANTERIOR")
        btn_anterior.setStyleSheet("background-color: #ccc; color: #666; font-weight: bold; font-size: 13px; padding: 8px; border-radius: 5px;")
        btn_anterior.setMinimumHeight(50)
        btn_anterior.clicked.connect(lambda: self.mudar_tela(self.tela_checklist_perguntas_1, "CHECKLIST_PERGUNTAS_1"))
        
        btn_proximo = QtWidgets.QPushButton("PRÓXIMO ▶")
        btn_proximo.setStyleSheet("background-color: #ccc; color: #666; font-weight: bold; font-size: 13px; padding: 8px; border-radius: 5px;")
        btn_proximo.setMinimumHeight(50)
        btn_proximo.clicked.connect(lambda: self.mudar_tela(self.tela_checklist_perguntas_3, "CHECKLIST_PERGUNTAS_3"))
        
        botoes_layout.addWidget(btn_anterior)
        botoes_layout.addWidget(btn_proximo)
        
        layout.addLayout(botoes_layout)
        
        tela.setLayout(layout)
        return tela

    # ========================================================================
    # TELA CHECKLIST - PERGUNTAS 5-6
    # ========================================================================
    def criar_tela_checklist_perguntas_3(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # Pergunta 5
        lbl_p5 = QtWidgets.QLabel(f"5. {self.perguntas[4]}")
        lbl_p5.setWordWrap(True)
        lbl_p5.setStyleSheet("font-size: 15px; font-weight: bold; padding: 5px; color: #333;")
        
        h_layout_5 = QtWidgets.QHBoxLayout()
        h_layout_5.setSpacing(10)
        
        btn_sim_5 = QtWidgets.QPushButton("✓ SIM")
        btn_sim_5.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
        btn_sim_5.setMinimumHeight(50)
        btn_sim_5.clicked.connect(lambda: self.marcar_resposta(4, "OK", btn_sim_5, btn_nao_5))
        
        btn_nao_5 = QtWidgets.QPushButton("✗ NÃO")
        btn_nao_5.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
        btn_nao_5.setMinimumHeight(50)
        btn_nao_5.clicked.connect(lambda: self.marcar_resposta(4, "NÃO OK", btn_sim_5, btn_nao_5))
        
        self.radios_ok.append(btn_sim_5)
        self.radios_nok.append(btn_nao_5)
        
        h_layout_5.addWidget(btn_sim_5)
        h_layout_5.addWidget(btn_nao_5)
        
        layout.addWidget(lbl_p5)
        layout.addLayout(h_layout_5)
        
        # Separador
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)
        
        # Pergunta 6
        lbl_p6 = QtWidgets.QLabel(f"6. {self.perguntas[5]}")
        lbl_p6.setWordWrap(True)
        lbl_p6.setStyleSheet("font-size: 15px; font-weight: bold; padding: 5px; color: #333;")
        
        h_layout_6 = QtWidgets.QHBoxLayout()
        h_layout_6.setSpacing(10)
        
        btn_sim_6 = QtWidgets.QPushButton("✓ SIM")
        btn_sim_6.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
        btn_sim_6.setMinimumHeight(50)
        btn_sim_6.clicked.connect(lambda: self.marcar_resposta(5, "OK", btn_sim_6, btn_nao_6))
        
        btn_nao_6 = QtWidgets.QPushButton("✗ NÃO")
        btn_nao_6.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
        btn_nao_6.setMinimumHeight(50)
        btn_nao_6.clicked.connect(lambda: self.marcar_resposta(5, "NÃO OK", btn_sim_6, btn_nao_6))
        
        self.radios_ok.append(btn_sim_6)
        self.radios_nok.append(btn_nao_6)
        
        h_layout_6.addWidget(btn_sim_6)
        h_layout_6.addWidget(btn_nao_6)
        
        layout.addWidget(lbl_p6)
        layout.addLayout(h_layout_6)
        
        layout.addStretch()
        
        # Botões de navegação
        botoes_layout = QtWidgets.QHBoxLayout()
        botoes_layout.setSpacing(10)
        
        btn_anterior = QtWidgets.QPushButton("◀ ANTERIOR")
        btn_anterior.setStyleSheet("background-color: #ccc; color: #666; font-weight: bold; font-size: 13px; padding: 8px; border-radius: 5px;")
        btn_anterior.setMinimumHeight(50)
        btn_anterior.clicked.connect(lambda: self.mudar_tela(self.tela_checklist_perguntas_2, "CHECKLIST_PERGUNTAS_2"))
        
        btn_proximo = QtWidgets.QPushButton("PRÓXIMO ▶")
        btn_proximo.setStyleSheet("background-color: #ccc; color: #666; font-weight: bold; font-size: 13px; padding: 8px; border-radius: 5px;")
        btn_proximo.setMinimumHeight(50)
        btn_proximo.clicked.connect(lambda: self.mudar_tela(self.tela_checklist_perguntas_4, "CHECKLIST_PERGUNTAS_4"))
        
        botoes_layout.addWidget(btn_anterior)
        botoes_layout.addWidget(btn_proximo)
        
        layout.addLayout(botoes_layout)
        
        tela.setLayout(layout)
        return tela

    # ========================================================================
    # TELA CHECKLIST - PERGUNTAS 7-8
    # ========================================================================
    def criar_tela_checklist_perguntas_4(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # Pergunta 7
        lbl_p7 = QtWidgets.QLabel(f"7. {self.perguntas[6]}")
        lbl_p7.setWordWrap(True)
        lbl_p7.setStyleSheet("font-size: 15px; font-weight: bold; padding: 5px; color: #333;")
        
        h_layout_7 = QtWidgets.QHBoxLayout()
        h_layout_7.setSpacing(10)
        
        btn_sim_7 = QtWidgets.QPushButton("✓ SIM")
        btn_sim_7.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
        btn_sim_7.setMinimumHeight(50)
        btn_sim_7.clicked.connect(lambda: self.marcar_resposta(6, "OK", btn_sim_7, btn_nao_7))
        
        btn_nao_7 = QtWidgets.QPushButton("✗ NÃO")
        btn_nao_7.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
        btn_nao_7.setMinimumHeight(50)
        btn_nao_7.clicked.connect(lambda: self.marcar_resposta(6, "NÃO OK", btn_sim_7, btn_nao_7))
        
        self.radios_ok.append(btn_sim_7)
        self.radios_nok.append(btn_nao_7)
        
        h_layout_7.addWidget(btn_sim_7)
        h_layout_7.addWidget(btn_nao_7)
        
        layout.addWidget(lbl_p7)
        layout.addLayout(h_layout_7)
        
        # Separador
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)
        
        # Pergunta 8
        lbl_p8 = QtWidgets.QLabel(f"8. {self.perguntas[7]}")
        lbl_p8.setWordWrap(True)
        lbl_p8.setStyleSheet("font-size: 15px; font-weight: bold; padding: 5px; color: #333;")
        
        h_layout_8 = QtWidgets.QHBoxLayout()
        h_layout_8.setSpacing(10)
        
        btn_sim_8 = QtWidgets.QPushButton("✓ SIM")
        btn_sim_8.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
        btn_sim_8.setMinimumHeight(50)
        btn_sim_8.clicked.connect(lambda: self.marcar_resposta(7, "OK", btn_sim_8, btn_nao_8))
        
        btn_nao_8 = QtWidgets.QPushButton("✗ NÃO")
        btn_nao_8.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
        btn_nao_8.setMinimumHeight(50)
        btn_nao_8.clicked.connect(lambda: self.marcar_resposta(7, "NÃO OK", btn_sim_8, btn_nao_8))
        
        self.radios_ok.append(btn_sim_8)
        self.radios_nok.append(btn_nao_8)
        
        h_layout_8.addWidget(btn_sim_8)
        h_layout_8.addWidget(btn_nao_8)
        
        layout.addWidget(lbl_p8)
        layout.addLayout(h_layout_8)
        
        layout.addStretch()
        
        # Botões de navegação
        botoes_layout = QtWidgets.QHBoxLayout()
        botoes_layout.setSpacing(10)
        
        btn_anterior = QtWidgets.QPushButton("◀ ANTERIOR")
        btn_anterior.setStyleSheet("background-color: #ccc; color: #666; font-weight: bold; font-size: 13px; padding: 8px; border-radius: 5px;")
        btn_anterior.setMinimumHeight(50)
        btn_anterior.clicked.connect(lambda: self.mudar_tela(self.tela_checklist_perguntas_3, "CHECKLIST_PERGUNTAS_3"))
        
        btn_proximo = QtWidgets.QPushButton("PRÓXIMO ▶")
        btn_proximo.setStyleSheet("background-color: #ccc; color: #666; font-weight: bold; font-size: 13px; padding: 8px; border-radius: 5px;")
        btn_proximo.setMinimumHeight(50)
        btn_proximo.clicked.connect(lambda: self.mudar_tela(self.tela_checklist_perguntas_5, "CHECKLIST_PERGUNTAS_5"))
        
        botoes_layout.addWidget(btn_anterior)
        botoes_layout.addWidget(btn_proximo)
        
        layout.addLayout(botoes_layout)
        
        tela.setLayout(layout)
        return tela

    # ========================================================================
    # TELA CHECKLIST - PERGUNTAS 9-10
    # ========================================================================
    def criar_tela_checklist_perguntas_5(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # Pergunta 9
        lbl_p9 = QtWidgets.QLabel(f"9. {self.perguntas[8]}")
        lbl_p9.setWordWrap(True)
        lbl_p9.setStyleSheet("font-size: 15px; font-weight: bold; padding: 5px; color: #333;")
        
        h_layout_9 = QtWidgets.QHBoxLayout()
        h_layout_9.setSpacing(10)
        
        btn_sim_9 = QtWidgets.QPushButton("✓ SIM")
        btn_sim_9.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
        btn_sim_9.setMinimumHeight(50)
        btn_sim_9.clicked.connect(lambda: self.marcar_resposta(8, "OK", btn_sim_9, btn_nao_9))
        
        btn_nao_9 = QtWidgets.QPushButton("✗ NÃO")
        btn_nao_9.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
        btn_nao_9.setMinimumHeight(50)
        btn_nao_9.clicked.connect(lambda: self.marcar_resposta(8, "NÃO OK", btn_sim_9, btn_nao_9))
        
        self.radios_ok.append(btn_sim_9)
        self.radios_nok.append(btn_nao_9)
        
        h_layout_9.addWidget(btn_sim_9)
        h_layout_9.addWidget(btn_nao_9)
        
        layout.addWidget(lbl_p9)
        layout.addLayout(h_layout_9)
        
        # Separador
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)
        
        # Pergunta 10
        lbl_p10 = QtWidgets.QLabel(f"10. {self.perguntas[9]}")
        lbl_p10.setWordWrap(True)
        lbl_p10.setStyleSheet("font-size: 15px; font-weight: bold; padding: 5px; color: #333;")
        
        h_layout_10 = QtWidgets.QHBoxLayout()
        h_layout_10.setSpacing(10)
        
        btn_sim_10 = QtWidgets.QPushButton("✓ SIM")
        btn_sim_10.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
        btn_sim_10.setMinimumHeight(50)
        btn_sim_10.clicked.connect(lambda: self.marcar_resposta(9, "OK", btn_sim_10, btn_nao_10))
        
        btn_nao_10 = QtWidgets.QPushButton("✗ NÃO")
        btn_nao_10.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
        btn_nao_10.setMinimumHeight(50)
        btn_nao_10.clicked.connect(lambda: self.marcar_resposta(9, "NÃO OK", btn_sim_10, btn_nao_10))
        
        self.radios_ok.append(btn_sim_10)
        self.radios_nok.append(btn_nao_10)
        
        h_layout_10.addWidget(btn_sim_10)
        h_layout_10.addWidget(btn_nao_10)
        
        layout.addWidget(lbl_p10)
        layout.addLayout(h_layout_10)
        
        layout.addStretch()
        
        # Botões de navegação
        botoes_layout = QtWidgets.QHBoxLayout()
        botoes_layout.setSpacing(10)
        
        btn_anterior = QtWidgets.QPushButton("◀ ANTERIOR")
        btn_anterior.setStyleSheet("background-color: #ccc; color: #666; font-weight: bold; font-size: 13px; padding: 8px; border-radius: 5px;")
        btn_anterior.setMinimumHeight(50)
        btn_anterior.clicked.connect(lambda: self.mudar_tela(self.tela_checklist_perguntas_4, "CHECKLIST_PERGUNTAS_4"))
        
        btn_proximo = QtWidgets.QPushButton("PRÓXIMO ▶")
        btn_proximo.setStyleSheet("background-color: #ccc; color: #666; font-weight: bold; font-size: 13px; padding: 8px; border-radius: 5px;")
        btn_proximo.setMinimumHeight(50)
        btn_proximo.clicked.connect(lambda: self.mudar_tela(self.tela_checklist_perguntas_6, "CHECKLIST_PERGUNTAS_6"))
        
        botoes_layout.addWidget(btn_anterior)
        botoes_layout.addWidget(btn_proximo)
        
        layout.addLayout(botoes_layout)
        
        tela.setLayout(layout)
        return tela


    # ========================================================================
    # TELA CHECKLIST - PERGUNTA 11 + OBSERVAÇÕES + SALVAR
    # ========================================================================
    def criar_tela_checklist_perguntas_6(self):
        tela = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # Pergunta 11
        lbl_p11 = QtWidgets.QLabel(f"11. {self.perguntas[10]}")
        lbl_p11.setWordWrap(True)
        lbl_p11.setStyleSheet("font-size: 15px; font-weight: bold; padding: 5px; color: #333;")
        
        h_layout_11 = QtWidgets.QHBoxLayout()
        h_layout_11.setSpacing(10)
        
        btn_sim_11 = QtWidgets.QPushButton("✓ SIM")
        btn_sim_11.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
        btn_sim_11.setMinimumHeight(50)
        btn_sim_11.clicked.connect(lambda: self.marcar_resposta(10, "OK", btn_sim_11, btn_nao_11))
        
        btn_nao_11 = QtWidgets.QPushButton("✗ NÃO")
        btn_nao_11.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
        btn_nao_11.setMinimumHeight(50)
        btn_nao_11.clicked.connect(lambda: self.marcar_resposta(10, "NÃO OK", btn_sim_11, btn_nao_11))
        
        self.radios_ok.append(btn_sim_11)
        self.radios_nok.append(btn_nao_11)
        
        h_layout_11.addWidget(btn_sim_11)
        h_layout_11.addWidget(btn_nao_11)
        
        layout.addWidget(lbl_p11)
        layout.addLayout(h_layout_11)
        
        # Separador
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)
        
        # Observações
        lbl_obs = QtWidgets.QLabel("Observações:")
        lbl_obs.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        
        self.txt_obs = QtWidgets.QTextEdit()
        self.txt_obs.setStyleSheet("background-color: white; padding: 10px; font-size: 13px; border: 1px solid #ccc; border-radius: 5px;")
        self.txt_obs.setMinimumHeight(80)
        
        layout.addWidget(lbl_obs)
        layout.addWidget(self.txt_obs)
        
        layout.addStretch()
        
        # Botões de navegação
        botoes_layout = QtWidgets.QHBoxLayout()
        botoes_layout.setSpacing(10)
        
        btn_anterior = QtWidgets.QPushButton("◀ ANTERIOR")
        btn_anterior.setStyleSheet("background-color: #ccc; color: #666; font-weight: bold; font-size: 13px; padding: 8px; border-radius: 5px;")
        btn_anterior.setMinimumHeight(50)
        btn_anterior.clicked.connect(lambda: self.mudar_tela(self.tela_checklist_perguntas_5, "CHECKLIST_PERGUNTAS_5"))
        
        btn_salvar = QtWidgets.QPushButton("SALVAR PDF")
        btn_salvar.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; font-size: 13px; padding: 8px; border-radius: 5px;")
        btn_salvar.setMinimumHeight(50)
        btn_salvar.clicked.connect(self.salvar_enviar_checklist)
        
        botoes_layout.addWidget(btn_anterior)
        botoes_layout.addWidget(btn_salvar)
        
        layout.addLayout(botoes_layout)
        
        tela.setLayout(layout)
        return tela

    # ========================================================================
    # MÉTODOS DO CHECKLIST
    # ========================================================================
    def iniciar_checklist(self):
        self.limpar_checklist()
        self.mudar_tela(self.tela_checklist_credenciais, "CHECKLIST_CREDENCIAIS")
        
    def cancelar_checklist(self):
        self.limpar_checklist()
        self.mudar_tela(self.tela_inicial, "TELA_INICIAL")
        
    def limpar_checklist(self):
        self.input_operador.clear()
        self.input_matricula.clear()
        self.txt_obs.clear()
        self.respostas_checklist.clear()  # Limpar respostas do checklist anterior
        
        for r_ok, r_nok in zip(self.radios_ok, self.radios_nok):
            r_ok.setAutoExclusive(False)
            r_nok.setAutoExclusive(False)
            r_ok.setChecked(False)
            r_nok.setChecked(False)
            r_ok.setAutoExclusive(True)
            r_nok.setAutoExclusive(True)
            
            # Resetar estilo dos botoes para estado inicial
            r_ok.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
            r_nok.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
            
            r_ok.setEnabled(False)
            r_nok.setEnabled(False)
            
        self.btn_proximo_chk.setEnabled(False)
        self.lbl_status_chk.setText("Aproxime seu crachá para preencher seus dados.")
        self.lbl_status_chk.setStyleSheet("color: #E65100; font-weight: bold; padding: 15px;")

    def habilitar_checklist(self):
        for r_ok, r_nok in zip(self.radios_ok, self.radios_nok):
            r_ok.setEnabled(True)
            r_nok.setEnabled(True)
        self.btn_proximo_chk.setEnabled(True)
        self.lbl_status_chk.setText("✓ Dados preenchidos. Clique em PRÓXIMO para responder as perguntas.")
        self.lbl_status_chk.setStyleSheet("color: #4CAF50; font-weight: bold; padding: 15px;")

    def marcar_resposta(self, idx, resposta, btn_sim, btn_nao):
        """Marca a resposta de uma pergunta com mudança visual"""
        if resposta == "OK":
            # SIM selecionado - fica verde preenchido
            btn_sim.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; font-size: 14px; padding: 8px; border-radius: 5px;")
            # NÃO volta ao estado normal
            btn_nao.setStyleSheet("background-color: #f0f0f0; color: #d32f2f; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #d32f2f; border-radius: 5px;")
            self.respostas_checklist[idx] = "OK"
        else:
            # NÃO selecionado - fica vermelho preenchido
            btn_nao.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold; font-size: 14px; padding: 8px; border-radius: 5px;")
            # SIM volta ao estado normal
            btn_sim.setStyleSheet("background-color: #f0f0f0; color: #4CAF50; font-weight: bold; font-size: 14px; padding: 8px; border: 2px solid #4CAF50; border-radius: 5px;")
            self.respostas_checklist[idx] = "NÃO OK"
    
    def salvar_enviar_checklist(self):
        # Validar se tudo foi respondido
        respostas = []
        tem_falha = False
        total_perguntas = len(self.perguntas)
        
        # Verificar respostas usando self.respostas_checklist
        for i in range(total_perguntas):
            if i in self.respostas_checklist:
                resposta = self.respostas_checklist[i]
                respostas.append(resposta)
                if resposta == "NÃO OK":
                    tem_falha = True
        
        # Verificar se todas as 11 perguntas foram respondidas
        if len(respostas) != total_perguntas:
            QtWidgets.QMessageBox.warning(self, "Atenção", f"Por favor, responda todos os {total_perguntas} itens do checklist antes de salvar.\n\nRespondidas: {len(respostas)}/{total_perguntas}")
            return
            
        # Preparar dados
        dados = {
            'operador': self.input_operador.text(),
            'matricula': self.input_matricula.text(),
            'equipamento': self.input_equipamento.text(),
            'data': datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            'respostas': respostas,
            'obs': self.txt_obs.toPlainText(),
            'status': "REPROVADO" if tem_falha else "APROVADO"
        }
        
        # Gerar PDF
        arquivo_pdf = self.gerar_pdf_checklist(dados)
        
        # Gerar PDF apenas (sem email)
        self.lbl_status_chk.setText("Gerando PDF, aguarde...")
        QtWidgets.QApplication.processEvents()
        
        if arquivo_pdf:
            # Fazer upload para GitHub
            print("[SISTEMA] Enviando PDF para GitHub...")
            self.git.fazer_upload_pdf(arquivo_pdf)
            
            # Popup de finalização
            if tem_falha:
                msg = f"✗ CHECKLIST REPROVADO\n\nPDF gerado: {arquivo_pdf}\n\nATENÇÃO: Operações suspensas devido a inconformidades."
                QtWidgets.QMessageBox.critical(self, "BLOQUEIO", msg)
            else:
                msg = f"✓ CHECKLIST APROVADO\n\nPDF gerado com sucesso!\n\n{arquivo_pdf}\n\n[GitHub] Upload realizado automaticamente"
                QtWidgets.QMessageBox.information(self, "Sucesso", msg)
            
            # Voltar para tela inicial
            self.limpar_checklist()
            self.mudar_tela(self.tela_inicial, "TELA_INICIAL")
        else:
            QtWidgets.QMessageBox.warning(self, "Erro", "Erro ao gerar PDF. Tente novamente.")
            self.lbl_status_chk.setText("Erro ao gerar PDF. Tente novamente.")

    def gerar_pdf_checklist(self, dados):
        try:
            # Criar pasta se não existir
            os.makedirs('./checklists', exist_ok=True)
            arquivo_pdf = f"./checklists/checklist_{dados['operador'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

            doc = SimpleDocTemplate(arquivo_pdf, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch, leftMargin=0.5*inch, rightMargin=0.5*inch)
            story = []
            styles = getSampleStyleSheet()
            
            # Estilo customizado
            style_titulo = ParagraphStyle(
                'TituloCustom',
                parent=styles['Heading1'],
                fontSize=16,
                textColor=colors.HexColor('#1a1a1a'),
                spaceAfter=12,
                alignment=1  # CENTER
            )
            
            # Título
            story.append(Paragraph("CHECKLIST DE SEGURANÇA", style_titulo))
            story.append(Paragraph("GUINCHO TRACIONADOR - EQUIPAMENTO 1172", style_titulo))
            story.append(Spacer(1, 0.2*inch))
            
            # Informações do Operador
            info_data = [
                ["Operador:", dados['operador']],
                ["Matrícula:", dados['matricula']],
                ["Equipamento:", dados['equipamento']],
                ["Data/Hora:", dados['data']],
                ["Status:", dados['status']]
            ]
            
            info_table = Table(info_data, colWidths=[1.3*inch, 4.7*inch])
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#E8E8E8')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#CCCCCC'))
            ]))
            
            story.append(info_table)
            story.append(Spacer(1, 0.25*inch))
            
            # Título da seção de perguntas
            story.append(Paragraph("ITENS VERIFICADOS:", styles['Heading2']))
            story.append(Spacer(1, 0.15*inch))
            
            # Construir tabela com perguntas e respostas
            perguntas_data = []
            for i, (pergunta, resposta) in enumerate(zip(self.perguntas, dados['respostas']), 1):
                # Usar símbolo visual para resposta
                if resposta == "OK":
                    resposta_visual = "✓ OK"
                else:
                    resposta_visual = "✗ NÃO OK"
                
                # Usar Paragraph para quebra de linha automática
                pergunta_para = Paragraph(
                    f"<b>{i}.</b> {pergunta}",
                    ParagraphStyle(
                        'PerguntaStyle',
                        parent=styles['Normal'],
                        fontSize=9,
                        leading=12,
                        alignment=0
                    )
                )
                
                perguntas_data.append([
                    pergunta_para,
                    resposta_visual
                ])
            
            # Criar tabela com largura adequada e altura mínima
            perguntas_table = Table(perguntas_data, colWidths=[4.2*inch, 1.3*inch])
            perguntas_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.white),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('TEXTCOLOR', (1, 1), (1, -1), colors.black),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (1, 1), (1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
                ('TOPPADDING', (0, 0), (-1, -1), 12),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#CCCCCC')),
                ('MINHEIGHT', (0, 1), (-1, -1), 0.4*inch)
            ]))
            
            story.append(perguntas_table)
            story.append(Spacer(1, 0.2*inch))
            
            # Observações
            story.append(Spacer(1, 0.15*inch))
            story.append(Paragraph("OBSERVAÇÕES:", styles['Heading2']))
            obs_text = dados['obs'] if dados['obs'] else "Nenhuma observação."
            story.append(Paragraph(obs_text, styles['Normal']))
            
            doc.build(story)
            print(f"✓ PDF gerado: {arquivo_pdf}")
            return arquivo_pdf
            
        except Exception as e:
            print(f"✗ Erro ao gerar PDF: {e}")
            return None

    # ========================================================================
    # PROCESSAMENTO DO RFID
    # ========================================================================



    def processar_rfid(self, uid):
        print(f"Processando UID: {uid} | Estado: {self.estado_atual}")
        
        # Processamento para o checklist
        if self.estado_atual == "CHECKLIST_CREDENCIAIS":
            func = self.dados.buscar_por_cracha(uid)
            if func:
                self.input_operador.setText(func['nome'])
                self.input_matricula.setText(func['matricula'])
                self.habilitar_checklist()
            else:
                QtWidgets.QMessageBox.warning(self, "Erro", "Crachá não encontrado na base de dados.")
            return

        # Ignora se não estiver na tela de leitura
        if self.central_widget.currentWidget() != self.tela_leitura:
            return
            
        # 1. LIBERAR EQUIPAMENTO
        if self.estado_atual == "LIBERAR_EQUIPAMENTO":
            func = self.dados.buscar_por_cracha(uid)
            
            if func:
                if func['status'] == 'H':
                    pass  # RC522: sem comando serial
                    self.mostrar_mensagem(
                        f"ACESSO AUTORIZADO\n\nEquipamento Liberado por 3 min.\n{func['nome']}", 
                        "#4CAF50", "white"
                    )
                else:
                    pass  # RC522: sem comando serial
                    self.mostrar_mensagem(
                        f"ACESSO NEGADO\n\nUsuário Desabilitado!\n{func['nome']}", 
                        "#F44336", "white"
                    )
            else:
                pass  # RC522: sem comando serial
                self.mostrar_mensagem("ACESSO NEGADO\n\nCrachá não cadastrado!", "#F44336", "white")
                
        # 2. HABILITAR USUÁRIO (PASSO 1 - MESTRE)
        elif self.estado_atual == "HABILITAR_USUARIO_MESTRE":
            if uid == UID_MESTRE:
                self.estado_atual = "HABILITAR_USUARIO_FINAL"
                self.lbl_instrucao.setText("Aproxime o crachá do USUÁRIO para HABILITAR")
                self.lbl_status.setText("Mestre autorizado! Aguardando usuário...")
                self.lbl_status.setStyleSheet("color: #4CAF50; padding: 20px; border: 2px solid #4CAF50; border-radius: 10px;")
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não é Mestre!", "#F44336", "white")
                
        # 2. HABILITAR USUÁRIO (PASSO 2 - FINAL)
        elif self.estado_atual == "HABILITAR_USUARIO_FINAL":
            func = self.dados.buscar_por_cracha(uid)
            if func:
                if self.dados.alterar_status(uid, 'H'):
                    self.mostrar_mensagem(f"SUCESSO\n\nUsuário HABILITADO!\n{func['nome']}", "#4CAF50", "white")
                else:
                    self.mostrar_mensagem("ERRO\n\nFalha ao salvar planilha!", "#F44336", "white")
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não cadastrado na base!", "#F44336", "white")
                
        # 3. DESABILITAR USUÁRIO (PASSO 1 - MESTRE)
        elif self.estado_atual == "DESABILITAR_USUARIO_MESTRE":
            if uid == UID_MESTRE:
                self.estado_atual = "DESABILITAR_USUARIO_FINAL"
                self.lbl_instrucao.setText("Aproxime o crachá do USUÁRIO para DESABILITAR")
                self.lbl_status.setText("Mestre autorizado! Aguardando usuário...")
                self.lbl_status.setStyleSheet("color: #4CAF50; padding: 20px; border: 2px solid #4CAF50; border-radius: 10px;")
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não é Mestre!", "#F44336", "white")
                
        # 3. DESABILITAR USUÁRIO (PASSO 2 - FINAL)
        elif self.estado_atual == "DESABILITAR_USUARIO_FINAL":
            func = self.dados.buscar_por_cracha(uid)
            if func:
                if self.dados.alterar_status(uid, 'D'):
                    self.mostrar_mensagem(f"SUCESSO\n\nUsuário DESABILITADO!\n{func['nome']}", "#FF9800", "white")
                else:
                    self.mostrar_mensagem("ERRO\n\nFalha ao salvar planilha!", "#F44336", "white")
            else:
                self.mostrar_mensagem("ERRO\n\nCrachá não cadastrado na base!", "#F44336", "white")

    def closeEvent(self, event):
        self.serial.parar()
        event.accept()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = SistemaGT()
    window.show()
    sys.exit(app.exec_())