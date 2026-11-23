"""Tabelas de códigos do SIH-RD, transcritas das fontes oficiais do DATASUS.

Fontes (FTP público do DATASUS, consultadas em 23/11/2026):
- Layout: Informe Técnico SIH, processamento 2016-03
  (ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Doc/IT_SIHSUS_1603.pdf).
- Códigos: tabelas de conversão do TabWin em TAB_SIH.zip
  (ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Auxiliar/TAB_SIH.zip),
  arquivo RD2008.DEF e CNV/IDENT.CNV, CNV/MORTES.CNV, CNV/SAIDAPERM.CNV, CNV/CARATEND.CNV,
  CNV/SEXO.CNV, CNV/IDADEDET.CNV, CNV/CID10CAP.CNV e DBF/TB_GRUPO.DBF (S09).
"""

from __future__ import annotations

FONTE_LAYOUT = (
    "Informe Técnico SIH, processamento 2016-03, Tabela 1 (layout RD*.dbf de 2008 em diante): "
    "ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Doc/IT_SIHSUS_1603.pdf"
)
FONTE_CODIGOS = (
    "Tabelas do TabWin para o SIH: "
    "ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Auxiliar/TAB_SIH.zip "
    "(RD2008.DEF e CNV/IDENT.CNV, CNV/MORTES.CNV, CNV/SAIDAPERM.CNV, CNV/CARATEND.CNV, CNV/SEXO.CNV, CNV/IDADEDET.CNV, CNV/CID10CAP.CNV, "
    "DBF/TB_GRUPO.DBF)"
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

# CNV/SEXO.CNV — "Sexo": 1 = masculino; 2 e 3 = feminino; o resto, ignorado.
SEXO = {
    "1": "M",
    "2": "F",
    "3": "F",
}

# CNV/IDADEDET.CNV — COD_IDADE + IDADE (3 dígitos): 2xx = dias, 3xx = meses, 4xx = anos,
# 5xx = 100 + xx anos; 000 e 999 = idade inválida.
COD_IDADE = {
    "2": "dias",
    "3": "meses",
    "4": "anos",
    "5": "centenas de anos (100 + IDADE)",
}

# CNV/CID10CAP.CNV — capítulos da CID-10 pela faixa da categoria (3 primeiros caracteres).
# (número, romano, nome, primeira categoria, última categoria). U00–U03 não tem capítulo no CNV.
CID10_CAPITULOS = (
    (1, "I", "Algumas doenças infecciosas e parasitárias", "A00", "B99"),
    (2, "II", "Neoplasias (tumores)", "C00", "D48"),
    (3, "III", "Doenças do sangue, órgãos hematopoéticos e transtornos imunitários", "D50", "D89"),
    (4, "IV", "Doenças endócrinas, nutricionais e metabólicas", "E00", "E90"),
    (5, "V", "Transtornos mentais e comportamentais", "F00", "F99"),
    (6, "VI", "Doenças do sistema nervoso", "G00", "G99"),
    (7, "VII", "Doenças do olho e anexos", "H00", "H59"),
    (8, "VIII", "Doenças do ouvido e da apófise mastoide", "H60", "H95"),
    (9, "IX", "Doenças do aparelho circulatório", "I00", "I99"),
    (10, "X", "Doenças do aparelho respiratório", "J00", "J99"),
    (11, "XI", "Doenças do aparelho digestivo", "K00", "K93"),
    (12, "XII", "Doenças da pele e do tecido subcutâneo", "L00", "L99"),
    (13, "XIII", "Doenças do sistema osteomuscular e do tecido conjuntivo", "M00", "M99"),
    (14, "XIV", "Doenças do aparelho geniturinário", "N00", "N99"),
    (15, "XV", "Gravidez, parto e puerpério", "O00", "O99"),
    (16, "XVI", "Algumas afecções originadas no período perinatal", "P00", "P96"),
    (17, "XVII", "Malformações congênitas, deformidades e anomalias cromossômicas", "Q00", "Q99"),
    (18, "XVIII", "Sintomas, sinais e achados anormais de exames clínicos e laboratoriais",
     "R00", "R99"),
    (19, "XIX", "Lesões, envenenamentos e outras consequências de causas externas", "S00", "T98"),
    (20, "XX", "Causas externas de morbidade e mortalidade", "V01", "Y98"),
    (21, "XXI", "Fatores que influenciam o estado de saúde e o contato com serviços de saúde",
     "Z00", "Z99"),
    (22, "XXII", "Códigos para propósitos especiais", "U04", "U99"),
)

# DBF/TB_GRUPO.DBF — grupos da Tabela SIGTAP (CO_GRUPO = 2 primeiros dígitos de PROC_REA;
# o RD2008.DEF agrupa PROC_REA por esse campo). Competência da tabela: 202407.
SIGTAP_GRUPOS = {
    "01": "Ações de promoção e prevenção em saúde",
    "02": "Procedimentos com finalidade diagnóstica",
    "03": "Procedimentos clínicos",
    "04": "Procedimentos cirúrgicos",
    "05": "Transplantes de órgãos, tecidos e células",
    "06": "Medicamentos",
    "07": "Órteses, próteses e materiais especiais",
    "08": "Ações complementares da atenção à saúde",
    "09": "Procedimentos para ofertas de cuidados integrados",
}

ROTULOS = {"IDENT": IDENT, "MORTE": MORTE, "COBRANCA": COBRANCA, "CAR_INT": CAR_INT}
