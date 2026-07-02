from __future__ import annotations

from pathlib import Path
from typing import Any

from recuperaai.bootstrap import create_engine
from recuperaai.build_info import version_label
from recuperaai.core.logging_config import current_log_path

DEMO_XML = '''<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe35240112345678000190550010000098761000098765">
      <ide><mod>55</mod><serie>1</serie><nNF>9876</nNF><tpNF>1</tpNF><idDest>1</idDest><dhEmi>2024-01-10T09:30:00-03:00</dhEmi></ide>
      <emit><CNPJ>12345678000190</CNPJ><xNome>Fornecedor Demonstração Ltda</xNome><enderEmit><UF>SP</UF></enderEmit><CRT>3</CRT></emit>
      <dest><CNPJ>00999888000177</CNPJ><xNome>Cliente Validação Visual SA</xNome><enderDest><UF>SP</UF></enderDest></dest>
      <det nItem="1"><prod><cProd>A1</cProd><xProd>Produto de demonstração</xProd><NCM>00000000</NCM><CFOP>1102</CFOP><qCom>2.0000</qCom><vUnCom>50.00</vUnCom><vProd>100.00</vProd></prod><imposto><ICMS><ICMS00><CST>00</CST><vBC>100.00</vBC><pICMS>18.00</pICMS><vICMS>18.00</vICMS></ICMS00></ICMS><PIS><PISAliq><CST>01</CST><vPIS>1.65</vPIS></PISAliq></PIS><COFINS><COFINSAliq><CST>01</CST><vCOFINS>7.60</vCOFINS></COFINSAliq></COFINS></imposto></det>
      <total><ICMSTot><vProd>100.00</vProd><vBC>100.00</vBC><vICMS>18.00</vICMS><vPIS>1.65</vPIS><vCOFINS>7.60</vCOFINS><vNF>100.00</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
</nfeProc>
'''

CHECKLIST_ITEMS = [
    ("Login", "Abrir o aplicativo, entrar com admin / Admin@12345 e confirmar que a troca de senha temporária é exigida."),
    ("Oportunidades", "Confirmar valores estimados de reembolso, valores confirmados, valores em validação, origem API e tabela por cliente."),
    ("Clientes", "Abrir o cliente 'Cliente Validação Visual' e conferir as abas Resumo, Dados, Contratos, Documentos, Notas, Importações, Inconsistências, Relatórios e Histórico."),
    ("Importações do cliente", "Na central do cliente, usar o ícone de anexar XML/PDF e conferir resumo com importados, duplicados e falhas."),
    ("Notas Fiscais", "Conferir se a nota de demonstração aparece com número, chave, valor, leitura e situação."),
    ("Ações de contexto", "Em notas/documentos/relatórios, conferir menus de contexto para visualizar, abrir, baixar e excluir quando o perfil permitir."),
    ("Análises", "Rodar análise do cliente selecionado, abrir uma nota por duplo clique e marcar um apontamento como Em revisão."),
    ("Relatórios", "Gerar PDF, Excel e CSV; abrir a aba Relatórios do cliente e conferir os arquivos listados."),
    ("Histórico", "Conferir se importação, análise, revisão e relatório aparecem no histórico do cliente."),
    ("Backup", "Criar backup local e confirmar que o caminho aparece em tela."),
    ("Perfis", "Criar usuário Consulta e confirmar que ele não vê Usuários, Configurações nem Backup e não consegue importar ou excluir."),
    ("Diagnóstico", "Gerar diagnóstico rápido e confirmar que os logs ficam em dados\\logs ou logs\\."),
]


def _write_demo_files(base: Path) -> dict[str, Path]:
    demo_dir = base / "validacao_visual_demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    xml_path = demo_dir / "nfe_demonstracao_com_atencao.xml"
    xml_path.write_text(DEMO_XML, encoding="utf-8")
    contract_path = demo_dir / "contrato_demonstracao.txt"
    contract_path.write_text("Contrato de demonstração para validação visual do RecuperaAI.", encoding="utf-8")
    doc_path = demo_dir / "documento_cliente_demonstracao.txt"
    doc_path.write_text("Documento enviado pelo cliente para validação visual.", encoding="utf-8")
    return {"xml": xml_path, "contract": contract_path, "document": doc_path}


def _write_checklist(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RecuperaAI — Checklist de Validação Visual",
        "",
        f"Versão: {result['version']}",
        f"Base local: `{result['base_dir']}`",
        f"Cliente de validação: **{result['client_name']}**",
        f"Arquivo técnico de diagnóstico: `{result.get('log_path') or 'não configurado nesta execução'}`",
        "",
        "## Roteiro tela por tela",
        "",
    ]
    for index, (title, description) in enumerate(CHECKLIST_ITEMS, start=1):
        lines.append(f"{index}. [ ] **{title}** — {description}")
    lines.extend([
        "",
        "## Resultado esperado",
        "",
        "- O operador não deve ver termos como parser, engine, SQLite, endpoint ou traceback.",
        "- Mensagens de erro devem ter texto claro e próximo passo.",
        "- A área do cliente deve concentrar documentos, notas, análises, inconsistências, relatórios e histórico.",
        "- A importação fiscal deve existir dentro da central do cliente, não como aba global separada.",
        "- A aba Oportunidades deve refletir os apontamentos salvos, sem prometer reembolso definitivo.",
        "- O sistema deve continuar funcionando localmente mesmo sem internet.",
        "",
        "## Dados criados para teste",
        "",
        f"- Cliente ID: `{result['client_id']}`",
        f"- Notas importadas: `{result['imported']}`",
        f"- Ignoradas/duplicadas: `{result['skipped']}`",
        f"- Falhas: `{result['failed']}`",
        f"- Inconsistências encontradas: `{result['findings']}`",
        f"- Relatórios gerados: `{result['reports']}`",
        "",
        "## Como registrar problema",
        "",
        "Quando alguma tela falhar, envie print da tela e os arquivos `logs\\*.log` e `dados\\logs\\recuperaai_app.log`.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def prepare_visual_validation(base_dir: str | None = None, portable: bool = False, checklist_output: str | None = None) -> dict[str, Any]:
    """Prepara massa de demonstração e checklist para validação visual no Windows.

    Esta rotina não abre a interface. Ela cria dados reais no banco local para que
    o usuário consiga abrir a aplicação e validar tela por tela com informações
    visíveis, em vez de testar com telas vazias.
    """
    engine = create_engine(base_dir=base_dir, portable=portable)
    engine.initialize()
    session = engine.auth.login("admin", "Admin@12345")

    files = _write_demo_files(engine.paths.data)
    existing = [c for c in engine.tool("clients").list_clients(session, "Cliente Validação Visual") if c.name == "Cliente Validação Visual"]
    if existing:
        client = existing[0]
    else:
        client = engine.tool("clients").create_client(
            session,
            "Cliente Validação Visual",
            "00.999.888/0001-77",
            "Responsável de Homologação",
            "validacao@recuperaai.local",
            notes="Cliente criado automaticamente para validação visual guiada.",
        )

    # Contrato e documento podem ser duplicados em execuções repetidas; duplicidade é tratada como não fatal.
    for category, file_path in [("contract", files["contract"]), ("corporate", files["document"] )]:
        try:
            engine.tool("documents").add_client_document(session, client.id, file_path, category)
        except Exception:
            pass

    import_result = engine.tool("invoices").import_files(session, client.id, [files["xml"]])
    findings = engine.tool("analysis").list_for_client(session, client.id)

    generated_reports = []
    for exporter in ("export_client_pdf", "export_client_xlsx", "export_client_csv"):
        try:
            generated_reports.append(str(getattr(engine.tool("reports"), exporter)(session, client.id)))
        except Exception:
            pass

    workspace = engine.tool("clients").get_client_workspace(session, client.id)
    checklist_path = Path(checklist_output).expanduser().resolve() if checklist_output else engine.paths.reports / "CHECKLIST_VALIDACAO_VISUAL.md"

    result = {
        "ok": True,
        "version": version_label(),
        "base_dir": str(engine.paths.base),
        "client_id": client.id,
        "client_name": client.name,
        "imported": len(import_result.get("imported", [])),
        "skipped": len(import_result.get("skipped", [])),
        "failed": len(import_result.get("failed", [])),
        "findings": len(findings),
        "reports": len(generated_reports),
        "workspace_sections": sorted(workspace.keys()),
        "checklist_path": str(checklist_path),
        "log_path": str(current_log_path()) if current_log_path() else None,
    }
    _write_checklist(checklist_path, result)
    engine.audit.record(session.user_id, "VALIDACAO_VISUAL_PREPARADA", "client", client.id, str(checklist_path))
    return result
