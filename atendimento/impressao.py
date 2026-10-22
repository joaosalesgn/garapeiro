"""Impressão térmica na fila do Windows para testes, cozinha e consumo."""
import sys
from datetime import datetime
from decimal import Decimal

class ErroImpressao(Exception):
    """Falha ao preparar ou enviar um trabalho à impressora."""


def _moeda(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")


def _quebrar_linha(texto: str, largura: int) -> list[str]:
    palavras = texto.split()
    linhas = []
    atual = ""
    for palavra in palavras:
        candidato = f"{atual} {palavra}".strip()
        if atual and len(candidato) > largura:
            linhas.append(atual)
            atual = palavra
        else:
            atual = candidato
    if atual:
        linhas.append(atual)
    return linhas


def _localizar(comanda) -> str:
    partes = []
    if comanda.mesa_id:
        partes.append(f"Mesa {comanda.mesa.numero}")
    if comanda.cliente_id:
        partes.append(comanda.cliente.nome)
    return " / ".join(partes) or comanda.get_canal_display()


def montar_comanda_cozinha(comanda, itens, agora=None) -> str:
    """Comanda de produção, sem valores e com caracteres grandes via ESC/POS."""
    agora = agora or datetime.now()
    linhas = [
        "\x1b@", "\x1bt\x02", "\x1bE\x01", "\x1d!\x11",
        "COZINHA", "\n", f"COMANDA #{comanda.pk}", "\n",
        *_quebrar_linha(_localizar(comanda), 24), "\n",
        agora.strftime("%d/%m/%Y %H:%M:%S"), "\n",
        "-" * 24, "\n", "\x1d!\x10",
    ]
    for item in itens:
        linhas.extend(_quebrar_linha(f"{item.quantidade} x {item.produto_nome}", 30))
        linhas.append("\n")
        if item.observacao:
            linhas.append("\x1d!\x00")
            linhas.extend(_quebrar_linha(f"OBS: {item.observacao}", 32))
            linhas.append("\n\x1d!\x10")
        for adicional in item.adicionais.all():
            linhas.append("\x1d!\x00")
            linhas.extend(_quebrar_linha(f"+ {adicional.quantidade} x {adicional.adicional_nome}", 24))
            linhas.append("\x1d!\x10")
            linhas.append("\n")
        linhas.append("\n")

    linhas.append("\x1d!\x11"),
    linhas.append("-" * 24),
    linhas.append("\n\n"),
    linhas.extend(["\x1d!\x00", "\n\n\n", "\x1dV\x00"])
    return "".join(linhas)


def montar_comprovante_consumo(comanda, itens, agora=None) -> str:
    """Lista os itens consumidos com valores individuais e total para conferência."""
    agora = agora or datetime.now()
    largura = 47
    linhas = [
        "\x1b@", "\x1bt\x02", "O GARAPEIRO CAFE".center(largura),
        "CONFERENCIA DE CONSUMO".center(largura), "-" * largura,
        *_quebrar_linha(_localizar(comanda), largura),
        agora.strftime("%d/%m/%Y %H:%M:%S"), "-" * largura,
    ]
    total = Decimal("0.00")
    
    linhas.append(f"{'QTDE':>4} {'PRODUTO':<19} {'VR. UNIT.':>10} {'VR. TOTAL':>10}")
    for item in itens:
        linhas.append(linha_colunas(item.quantidade, item.produto_nome, item.preco_unitario, item.total, False))
        total += item.total

        for adicional in item.adicionais.all():
            linhas.append(linha_colunas(adicional.quantidade, f"+ {adicional.adicional_nome}", adicional.preco_unitario, adicional.total, True))
            total += adicional.total
    linhas.extend(["-" * largura, "\x1d!\x10", f"TOTAL: {_moeda(total)}", "\n\n\n\n\n\x1dV\x00"])
    return "\n".join(linhas)


def linha_colunas(qtde, produto, unitario, total, isAdicional):
    produto = str(produto)[:19]  # limita o nome para não invadir as colunas
    
    if isAdicional:
        return (f"{"  ":>4} " f"{produto:<19} " f"{_moeda(unitario):>10} " f"{_moeda(total):>10}")
    
    return (f"{str(qtde):>4} " f"{produto:<19} " f"{_moeda(unitario):>10} " f"{_moeda(total):>10}")


def imprimir_texto_windows(texto: str, nome_impressora: str) -> None:
    """Envia bytes ESC/POS à fila configurada do Windows."""
    if sys.platform != "win32":
        raise ErroImpressao("A impressão pela fila do Windows só pode ser executada no computador Windows do sistema.")
    try:
        import ctypes
        from ctypes import wintypes

        class DOC_INFO_1(ctypes.Structure):
            _fields_ = [("pDocName", wintypes.LPWSTR), ("pOutputFile", wintypes.LPWSTR), ("pDatatype", wintypes.LPWSTR)]

        spool = ctypes.WinDLL("winspool.drv", use_last_error=True)
        abrir = spool.OpenPrinterW
        abrir.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
        abrir.restype = wintypes.BOOL
        fechar = spool.ClosePrinter
        fechar.argtypes = [wintypes.HANDLE]
        fechar.restype = wintypes.BOOL
        iniciar_doc = spool.StartDocPrinterW
        iniciar_doc.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(DOC_INFO_1)]
        iniciar_doc.restype = wintypes.DWORD
        iniciar_pagina = spool.StartPagePrinter
        iniciar_pagina.argtypes = [wintypes.HANDLE]
        iniciar_pagina.restype = wintypes.BOOL
        escrever = spool.WritePrinter
        escrever.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        escrever.restype = wintypes.BOOL
        finalizar_pagina = spool.EndPagePrinter
        finalizar_pagina.argtypes = [wintypes.HANDLE]
        finalizar_pagina.restype = wintypes.BOOL
        finalizar_doc = spool.EndDocPrinter
        finalizar_doc.argtypes = [wintypes.HANDLE]
        finalizar_doc.restype = wintypes.BOOL

        handle = wintypes.HANDLE()
        if not abrir(nome_impressora, ctypes.byref(handle), None):
            raise OSError(ctypes.get_last_error(), "Não foi possível abrir a fila da impressora")
        try:
            info = DOC_INFO_1("Impressao - O Garapeiro", None, "RAW")
            if not iniciar_doc(handle, 1, ctypes.byref(info)):
                raise OSError(ctypes.get_last_error(), "Não foi possível iniciar o trabalho de impressão")
            try:
                if not iniciar_pagina(handle):
                    raise OSError(ctypes.get_last_error(), "Não foi possível iniciar a página de impressão")
                conteudo = texto.encode("cp850", errors="replace")
                buffer = ctypes.create_string_buffer(conteudo)
                escritos = wintypes.DWORD()
                if not escrever(handle, buffer, len(conteudo), ctypes.byref(escritos)):
                    raise OSError(ctypes.get_last_error(), "Falha ao enviar os dados para a impressora")
                if escritos.value != len(conteudo):
                    raise OSError("O Windows enviou apenas parte do conteúdo à impressora")
                if not finalizar_pagina(handle):
                    raise OSError(ctypes.get_last_error(), "Não foi possível concluir a página de impressão")
            finally:
                finalizar_doc(handle)
        finally:
            fechar(handle)
    except ErroImpressao:
        raise
    except Exception as exc:
        raise ErroImpressao(
            f"Não foi possível imprimir na fila '{nome_impressora}'. Confira se ela está instalada, ligada e pronta. Detalhe: {exc}"
        ) from exc


def imprimir_itens_cozinha(comanda, itens, nome_impressora: str) -> None:
    imprimir_texto_windows(montar_comanda_cozinha(comanda, itens), nome_impressora)


def imprimir_itens_consumo(comanda, itens, nome_impressora: str) -> None:
    imprimir_texto_windows(montar_comprovante_consumo(comanda, itens), nome_impressora)
