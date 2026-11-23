"""Tabelas de códigos do SIH-RD, transcritas das fontes oficiais do DATASUS.

Fontes (FTP público do DATASUS, consultadas em 23/11/2026):
- Layout: Informe Técnico SIH, processamento 2016-03
  (ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Doc/IT_SIHSUS_1603.pdf).
- Códigos: tabelas de conversão do TabWin em TAB_SIH.zip
  (ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Auxiliar/TAB_SIH.zip),
  arquivo RD2008.DEF e CNV/IDENT.CNV, CNV/MORTES.CNV, CNV/SAIDAPERM.CNV, CNV/CARATEND.CNV.
"""

from __future__ import annotations

FONTE_LAYOUT = (
    "Informe Técnico SIH, processamento 2016-03, Tabela 1 (layout RD*.dbf de 2008 em diante): "
    "ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Doc/IT_SIHSUS_1603.pdf"
)
FONTE_CODIGOS = (
    "Tabelas do TabWin para o SIH: "
    "ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Auxiliar/TAB_SIH.zip "
    "(RD2008.DEF e CNV/IDENT.CNV, CNV/MORTES.CNV, CNV/SAIDAPERM.CNV, CNV/CARATEND.CNV)"
)

# CNV/IDENT.CNV — "Tipo de AIH". Qualquer outro dígito o TabWin agrupa como "Outras/ignorado".
IDENT = {
    "1": "Normal",
    "5": "Longa permanência",
}

# CNV/MORTES.CNV — "Óbitos".
MORTE = {
    "1": "Com óbito",
    "0": "Sem óbito",
}

# CNV/SAIDAPERM.CNV — "Motivo Saída/Permanência" (campo COBRANCA).
COBRANCA = {
    "11": "Alta curado",
    "12": "Alta melhorado",
    "13": "Alta da mãe/puérpera e permanência do recém-nascido",
    "14": "Alta a pedido",
    "15": "Alta com previsão de retorno p/ acompanhamento do paciente",
    "16": "Alta por evasão",
    "17": "Alta da mãe/puérpera e do recém-nascido",
    "18": "Alta por outros motivos",
    "19": "Alta de paciente agudo em psiquiatria",
    "21": "Permanência por características próprias da doença",
    "22": "Permanência por intercorrência",
    "23": "Permanência por impossibilidade sócio-familiar",
    "24": "Permanência proc. doação órg., tec., cél. — doador vivo",
    "25": "Permanência proc. doação órg., tec., cél. — doador morto",
    "26": "Permanência por mudança de procedimento",
    "27": "Permanência por reoperação",
    "28": "Permanência por outros motivos",
    "29": "Transferência para internação domiciliar",
    "31": "Transferência para outro estabelecimento",
    "32": "Transferência para internação domiciliar",
    "41": "Óbito com DO fornecida pelo médico assistente",
    "42": "Óbito com DO fornecida pelo IML",
    "43": "Óbito com DO fornecida pelo SVO",
    "51": "Encerramento administrativo",
    "61": "Alta da mãe/puérpera e do recém-nascido",
    "62": "Alta da mãe/puérpera e permanência do recém-nascido",
    "63": "Alta da mãe/puérpera e óbito do recém-nascido",
    "64": "Alta da mãe/puérpera com óbito fetal",
    "65": "Óbito da gestante e do concepto",
    "66": "Óbito da mãe/puérpera e alta do recém-nascido",
    "67": "Óbito da mãe/puérpera e permanência do recém-nascido",
}

COBRANCA_TRANSFERENCIA = frozenset({"29", "31", "32"})
# 2x: a AIH fecha, mas o paciente continua internado (D01, tratamento 6).
COBRANCA_PERMANENCIA = frozenset({"21", "22", "23", "24", "25", "26", "27", "28"})
COBRANCA_OBITO = frozenset({"41", "42", "43", "65", "66", "67"})

# CNV/CARATEND.CNV — "Caráter atendimento".
CAR_INT = {
    "01": "Eletivo",
    "02": "Urgência",
    "03": "Acidente no local de trabalho ou a serviço da empresa",
    "04": "Acidente no trajeto para o trabalho",
    "05": "Outros tipos de acidente de trânsito",
    "06": "Outros tipos de lesões e envenenamentos por agentes químicos ou físicos",
}

ROTULOS = {"IDENT": IDENT, "MORTE": MORTE, "COBRANCA": COBRANCA, "CAR_INT": CAR_INT}
