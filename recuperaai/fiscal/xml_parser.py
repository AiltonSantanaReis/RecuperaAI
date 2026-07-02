from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from recuperaai.fiscal.key_utils import normalize_invoice_key
from recuperaai.fiscal.models import InvoiceData, InvoiceItem


NFSE_KEY_PREFIX = 'SERVICONFSE'
UNSAFE_XML_MARKERS = (b'<!doctype', b'<!entity')


def _reject_unsafe_xml(path: Path) -> None:
    with path.open('rb') as fh:
        head = fh.read(8192).lower()
    if any(marker in head for marker in UNSAFE_XML_MARKERS):
        raise ValueError('XML com DTD ou entidade externa não é aceito por segurança.')


def _tag(el: ET.Element) -> str:
    return el.tag.split('}', 1)[-1] if '}' in el.tag else el.tag


def _norm_name(name: str) -> str:
    return re.sub(r'[^0-9a-z]', '', name.lower())


def _matches(el: ET.Element, names: Iterable[str]) -> bool:
    wanted = {_norm_name(name) for name in names}
    return _norm_name(_tag(el)) in wanted


def _all(parent: ET.Element | None, names: Iterable[str]) -> list[ET.Element]:
    if parent is None:
        return []
    return [el for el in parent.iter() if el is not parent and _matches(el, names)]


def _first(parent: ET.Element | None, names: Iterable[str]) -> ET.Element | None:
    found = _all(parent, names)
    return found[0] if found else None


def _direct(parent: ET.Element | None, names: Iterable[str]) -> ET.Element | None:
    if parent is None:
        return None
    for child in list(parent):
        if _matches(child, names):
            return child
    return None


def _first_present(*items: ET.Element | None) -> ET.Element | None:
    for item in items:
        if item is not None:
            return item
    return None


def _first_text(parent: ET.Element | None, names: Iterable[str]) -> str | None:
    if parent is None:
        return None
    for el in parent.iter():
        if _matches(el, names) and el.text and el.text.strip():
            return el.text.strip()
    return None


def _direct_text(parent: ET.Element | None, names: Iterable[str]) -> str | None:
    if parent is None:
        return None
    for child in list(parent):
        if _matches(child, names) and child.text and child.text.strip():
            return child.text.strip()
    return None


def _text_from_first(parent: ET.Element | None, container_names: Iterable[str], value_names: Iterable[str]) -> str | None:
    container = _first(parent, container_names)
    return _first_text(container, value_names)


def _attr_key(inf: ET.Element | None, prefixes: tuple[str, ...]) -> str | None:
    if inf is None:
        return None
    raw = inf.attrib.get('Id') or inf.attrib.get('ID') or inf.attrib.get('id')
    if not raw:
        return None
    for prefix in prefixes:
        if raw.upper().startswith(prefix.upper()):
            raw = raw[len(prefix):]
            break
    return normalize_invoice_key(raw)


def _float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace('\xa0', '').replace('R$', '').strip()
    if ',' in text and '.' in text:
        text = text.replace('.', '').replace(',', '.')
    else:
        text = text.replace(',', '.')
    try:
        return float(text)
    except Exception:
        return None


def _digits(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r'\D', '', value)
    return digits or None


def _document_text(parent: ET.Element | None) -> str | None:
    if parent is None:
        return None
    cnpj = _first_text(parent, ['CNPJ', 'Cnpj'])
    cpf = _first_text(parent, ['CPF', 'Cpf'])
    cpf_cnpj = _first(parent, ['CpfCnpj', 'CPFCNPJ', 'CpfCnpjPrestador', 'CpfCnpjTomador'])
    nested = _first_text(cpf_cnpj, ['CNPJ', 'Cnpj', 'CPF', 'Cpf']) if cpf_cnpj is not None else None
    return _digits(cnpj or cpf or nested or _first_text(parent, ['CpfCnpj', 'CPFCNPJ']))


def _state_text(parent: ET.Element | None) -> str | None:
    if parent is None:
        return None
    # Prefere UF dentro de endereço para evitar confusão com tags fiscais de outro escopo.
    address = _first(parent, ['enderEmit', 'enderDest', 'enderReme', 'enderReceb', 'Endereco', 'EnderecoPrestador', 'EnderecoTomador'])
    raw = _first_text(address, ['UF']) or _direct_text(parent, ['UF'])
    if not raw:
        return None
    raw = raw.strip().upper()
    return raw if re.fullmatch(r'[A-Z]{2}', raw) else None


def _operation_type(tp_nf: str | None) -> str | None:
    if tp_nf == '0':
        return 'entrada'
    if tp_nf == '1':
        return 'saida'
    return None


def _operation_scope(id_dest: str | None) -> str | None:
    return {'1': 'interna', '2': 'interestadual', '3': 'exterior'}.get(id_dest or '')


def _name_text(parent: ET.Element | None) -> str | None:
    return _first_text(parent, ['xNome', 'RazaoSocial', 'RazaoSocialPrestador', 'RazaoSocialTomador', 'Nome', 'NomeFantasia'])


def _taxes(parent: ET.Element | None, mapping: dict[str, str]) -> dict[str, float]:
    values: dict[str, float] = {}
    for source, target in mapping.items():
        value = _float(_first_text(parent, [source]))
        if value is not None:
            values[target] = value
    return values


def _first_item_tax_code(parent: ET.Element | None, names: list[str]) -> str | None:
    if parent is None:
        return None
    icms = _first_present(_first(parent, ['ICMS']), parent)
    return _first_text(icms, names)


class FiscalXmlParser:
    """Parser tolerante para documentos fiscais XML brasileiros.

    Cobertura desta etapa:
    - NF-e modelo 55 e NFC-e modelo 65, incluindo XML autorizado em nfeProc.
    - CT-e modelo 57, com item sintético de serviço de transporte.
    - NFS-e em layouts ABRASF/prefeituras comuns, com chave canônica quando há
      número, código de verificação e documento do prestador.

    Quando uma chave fiscal confiável não existe no XML, o parser não inventa uma
    chave fraca: retorna aviso para que a importação continue sem duplicidade por chave.
    """

    def parse(self, path: Path) -> InvoiceData:
        _reject_unsafe_xml(path)
        tree = ET.parse(path)
        root = tree.getroot()

        if self._looks_like_cte(root):
            return self._parse_cte(root)
        if self._looks_like_nfe(root):
            return self._parse_nfe(root)
        if self._looks_like_nfse(root):
            return self._parse_nfse(root)

        data = self._parse_generic_xml(root)
        data.warnings.append('Tipo de XML fiscal não reconhecido com segurança.')
        return data

    def _looks_like_nfe(self, root: ET.Element) -> bool:
        inf = _first(root, ['infNFe'])
        model = _first_text(_first(inf, ['ide']), ['mod']) if inf is not None else None
        return inf is not None and model in {None, '55', '65'}

    def _looks_like_cte(self, root: ET.Element) -> bool:
        return _first(root, ['infCte', 'infCTe']) is not None or _first_text(root, ['chCTe']) is not None

    def _looks_like_nfse(self, root: ET.Element) -> bool:
        local_tags = {_norm_name(_tag(el)) for el in root.iter()}
        return bool(
            {'infnfse', 'nfse', 'compnfse', 'listanfse', 'gerarnfseresposta'} & local_tags
            or _first_text(root, ['CodigoVerificacao', 'ChaveNfse', 'ChaveNFS-e'])
        )

    def _parse_nfe(self, root: ET.Element) -> InvoiceData:
        inf = _first_present(_first(root, ['infNFe']), root)
        ide = _first(inf, ['ide'])
        emit = _first(inf, ['emit'])
        dest = _first(inf, ['dest'])
        total = _first_present(_first(inf, ['ICMSTot']), _first(inf, ['ISSQNtot']), _first(inf, ['total']), inf)
        model = _first_text(ide, ['mod'])
        document_type = 'NFC-e' if model == '65' else 'NF-e'
        invoice_key = (
            _attr_key(inf, ('NFe', 'NFCe'))
            or normalize_invoice_key(_first_text(root, ['chNFe', 'ChaveNFe', 'ChaveAcesso']))
            or self._extract_access_key_from_qrcode(root)
        )

        items: list[InvoiceItem] = []
        for det in _all(inf, ['det']):
            prod = _first_present(_first(det, ['prod']), det)
            imposto = _first(det, ['imposto'])
            item = InvoiceItem(
                code=_first_text(prod, ['cProd']),
                description=_first_text(prod, ['xProd', 'DescricaoProduto', 'Discriminacao']),
                ncm=_first_text(prod, ['NCM']),
                cfop=_first_text(prod, ['CFOP']),
                cest=_first_text(prod, ['CEST']),
                cst=_first_item_tax_code(imposto, ['CST']),
                csosn=_first_item_tax_code(imposto, ['CSOSN']),
                unit=_first_text(prod, ['uCom', 'Unidade']),
                quantity=_float(_first_text(prod, ['qCom', 'Quantidade'])),
                unit_value=_float(_first_text(prod, ['vUnCom', 'ValorUnitario'])),
                total_value=_float(_first_text(prod, ['vProd', 'ValorTotal'])),
                discount=_float(_first_text(prod, ['vDesc', 'ValorDesconto'])),
                taxes=_taxes(imposto, {
                    'vICMS': 'ICMS',
                    'vICMSST': 'ICMS_ST',
                    'vFCP': 'FCP',
                    'vIPI': 'IPI',
                    'vPIS': 'PIS',
                    'vCOFINS': 'COFINS',
                    'vISSQN': 'ISS',
                    'vTotTrib': 'TotalTributos',
                }),
            )
            items.append(item)

        data = InvoiceData(
            source_type='xml',
            invoice_key=invoice_key,
            model=model,
            document_type=document_type,
            number=_first_text(ide, ['nNF']),
            series=_first_text(ide, ['serie']),
            issue_date=_first_text(ide, ['dhEmi', 'dEmi']),
            issuer_name=_name_text(emit),
            issuer_document=_document_text(emit),
            recipient_name=_name_text(dest),
            recipient_document=_document_text(dest),
            issuer_state=_state_text(emit),
            recipient_state=_state_text(dest),
            issuer_tax_regime=_first_text(emit, ['CRT']),
            operation_type=_operation_type(_first_text(ide, ['tpNF'])),
            operation_scope=_operation_scope(_first_text(ide, ['idDest'])),
            total_amount=_float(_first_text(total, ['vNF', 'vCFe'])),
            products_total=_float(_first_text(total, ['vProd'])),
            services_total=_float(_first_text(total, ['vServ'])),
            taxes=_taxes(total, {
                'vICMS': 'ICMS',
                'vICMSST': 'ICMS_ST',
                'vFCP': 'FCP',
                'vIPI': 'IPI',
                'vPIS': 'PIS',
                'vCOFINS': 'COFINS',
                'vISS': 'ISS',
                'vTotTrib': 'TotalTributos',
                'vII': 'II',
                'vFrete': 'Frete',
                'vDesc': 'Desconto',
                'vOutro': 'Outros',
            }),
            items=items,
        )
        self._add_common_warnings(data)
        return data

    def _parse_cte(self, root: ET.Element) -> InvoiceData:
        inf = _first_present(_first(root, ['infCte', 'infCTe']), root)
        ide = _first(inf, ['ide'])
        emit = _first(inf, ['emit'])
        dest = _first_present(_first(inf, ['dest']), _first(inf, ['receb']), _first(inf, ['rem']))
        vprest = _first_present(_first(inf, ['vPrest']), inf)
        imp = _first_present(_first(inf, ['imp']), inf)
        inf_carga = _first(inf, ['infCarga'])
        model = _first_text(ide, ['mod']) or '57'
        total_amount = _float(_first_text(vprest, ['vTPrest', 'vRec']))
        description = _first_text(inf_carga, ['proPred', 'xOutCat']) or _first_text(ide, ['natOp']) or 'Serviço de transporte'
        cfop = _first_text(ide, ['CFOP', 'cfop'])

        items = [InvoiceItem(
            description=description,
            cfop=cfop,
            total_value=total_amount,
            taxes=_taxes(imp, {'vICMS': 'ICMS', 'vTotTrib': 'TotalTributos'}),
        )]

        data = InvoiceData(
            source_type='xml',
            invoice_key=_attr_key(inf, ('CTe',)) or normalize_invoice_key(_first_text(root, ['chCTe', 'ChaveCTe', 'ChaveAcesso'])),
            model=model,
            document_type='CT-e',
            number=_first_text(ide, ['nCT', 'Numero']),
            series=_first_text(ide, ['serie', 'Serie']),
            issue_date=_first_text(ide, ['dhEmi', 'dEmi', 'DataEmissao']),
            issuer_name=_name_text(emit),
            issuer_document=_document_text(emit),
            recipient_name=_name_text(dest),
            recipient_document=_document_text(dest),
            issuer_state=_state_text(emit),
            recipient_state=_state_text(dest),
            operation_type='saida',
            total_amount=total_amount,
            services_total=total_amount,
            taxes=_taxes(imp, {
                'vICMS': 'ICMS',
                'vTotTrib': 'TotalTributos',
                'vBC': 'BaseICMS',
            }),
            items=items,
        )
        self._add_common_warnings(data)
        return data

    def _parse_nfse(self, root: ET.Element) -> InvoiceData:
        inf = _first_present(_first(root, ['InfNfse', 'infNfse', 'InfNFSe', 'infNFSe']), root)
        declaracao = _first(root, ['InfDeclaracaoPrestacaoServico', 'DeclaracaoPrestacaoServico'])
        scope = _first_present(declaracao, inf)
        servico = _first_present(_first(scope, ['Servico']), _first(inf, ['Servico']), scope)
        nfse_values = _first(inf, ['ValoresNfse'])
        service_values = _first(servico, ['Valores'])
        valores = _first_present(nfse_values, service_values, _first(inf, ['Valores']), servico)
        prestador = _first_present(_first(scope, ['PrestadorServico', 'Prestador']), _first(inf, ['PrestadorServico', 'Prestador']))
        tomador = _first_present(_first(scope, ['TomadorServico', 'Tomador']), _first(inf, ['TomadorServico', 'Tomador']))

        issuer_document = _document_text(prestador)
        recipient_document = _document_text(tomador)
        number = _direct_text(inf, ['Numero', 'NumeroNfse']) or _first_text(inf, ['NumeroNfse', 'NumeroNota', 'Numero'])
        verification = _first_text(inf, ['CodigoVerificacao', 'CodigoVerificacaoNfse']) or _first_text(root, ['CodigoVerificacao'])
        explicit_key = normalize_invoice_key(_first_text(root, ['ChaveNfse', 'ChaveNFSe', 'ChaveNFS-e', 'ChaveAcesso']))
        invoice_key = explicit_key or self._canonical_nfse_key(issuer_document, number, verification)
        service_value = _float(
            _first_text(service_values, ['ValorServicos', 'ValorServico', 'ValorTotalServicos'])
            or _first_text(nfse_values, ['ValorServicos', 'ValorServico', 'ValorTotalServicos'])
            or _first_text(valores, ['ValorServicos', 'ValorServico', 'ValorTotalServicos'])
        )
        liquid_value = _float(
            _first_text(nfse_values, ['ValorLiquidoNfse', 'ValorLiquidoNFSe', 'ValorNota', 'ValorTotal'])
            or _first_text(service_values, ['ValorLiquidoNfse', 'ValorLiquidoNFSe', 'ValorNota', 'ValorTotal'])
            or _first_text(valores, ['ValorLiquidoNfse', 'ValorLiquidoNFSe', 'ValorNota', 'ValorTotal'])
        )
        total_amount = liquid_value if liquid_value is not None else service_value
        service_code = _first_text(servico, ['ItemListaServico', 'CodigoServico', 'CodigoTributacaoMunicipio', 'CodigoCnae'])
        description = _first_text(servico, ['Discriminacao', 'DescricaoServico', 'Descricao']) or 'Serviço'

        item = InvoiceItem(
            code=service_code,
            service_code=service_code,
            description=description,
            quantity=1.0 if total_amount is not None else None,
            total_value=service_value if service_value is not None else total_amount,
            taxes=_taxes(valores, {
                'ValorIss': 'ISS',
                'ValorISS': 'ISS',
                'ValorPis': 'PIS',
                'ValorPIS': 'PIS',
                'ValorCofins': 'COFINS',
                'ValorCOFINS': 'COFINS',
                'ValorInss': 'INSS',
                'ValorINSS': 'INSS',
                'ValorIr': 'IR',
                'ValorIR': 'IR',
                'ValorCsll': 'CSLL',
                'ValorCSLL': 'CSLL',
            }),
        )

        data = InvoiceData(
            source_type='xml',
            invoice_key=invoice_key,
            model='NFS-e',
            document_type='NFS-e',
            number=number,
            series=_first_text(inf, ['Serie', 'serie']),
            issue_date=_first_text(inf, ['DataEmissao', 'DataEmissaoNfse', 'Competencia']),
            issuer_name=_name_text(prestador),
            issuer_document=issuer_document,
            recipient_name=_name_text(tomador),
            recipient_document=recipient_document,
            issuer_state=_state_text(prestador),
            recipient_state=_state_text(tomador),
            operation_type='servico',
            total_amount=total_amount,
            services_total=service_value,
            taxes=_taxes(valores, {
                'ValorIss': 'ISS',
                'ValorISS': 'ISS',
                'ValorPis': 'PIS',
                'ValorPIS': 'PIS',
                'ValorCofins': 'COFINS',
                'ValorCOFINS': 'COFINS',
                'ValorInss': 'INSS',
                'ValorINSS': 'INSS',
                'ValorIr': 'IR',
                'ValorIR': 'IR',
                'ValorCsll': 'CSLL',
                'ValorCSLL': 'CSLL',
                'BaseCalculo': 'BaseCalculo',
                'Aliquota': 'Aliquota',
                'ValorDeducoes': 'Deducoes',
                'DescontoIncondicionado': 'DescontoIncondicionado',
                'DescontoCondicionado': 'DescontoCondicionado',
            }),
            items=[item] if (description or total_amount is not None or service_value is not None) else [],
        )
        if not explicit_key and data.invoice_key:
            data.warnings.append('Chave canônica de NFS-e gerada a partir de prestador, número e código de verificação.')
        self._add_common_warnings(data)
        return data

    def _parse_generic_xml(self, root: ET.Element) -> InvoiceData:
        invoice_key = normalize_invoice_key(_first_text(root, ['chNFe', 'chCTe', 'ChaveNFe', 'ChaveCTe', 'ChaveNfse', 'ChaveAcesso']))
        total = _float(_first_text(root, ['vNF', 'ValorLiquidoNfse', 'ValorServicos', 'ValorTotal', 'vTPrest']))
        data = InvoiceData(
            source_type='xml',
            invoice_key=invoice_key,
            model=_first_text(root, ['mod', 'Modelo']),
            document_type='XML fiscal',
            number=_first_text(root, ['nNF', 'nCT', 'Numero', 'NumeroNfse']),
            series=_first_text(root, ['serie', 'Serie']),
            issue_date=_first_text(root, ['dhEmi', 'dEmi', 'DataEmissao']),
            issuer_name=_first_text(root, ['xNome', 'RazaoSocial', 'Nome']),
            issuer_document=_digits(_first_text(root, ['CNPJ', 'CPF', 'CpfCnpj'])),
            total_amount=total,
        )
        self._add_common_warnings(data)
        return data

    def _extract_access_key_from_qrcode(self, root: ET.Element) -> str | None:
        qr = _first_text(root, ['qrCode', 'QRCode'])
        if not qr:
            return None
        match = re.search(r'\b(\d{44})\b', qr)
        return normalize_invoice_key(match.group(1)) if match else None

    def _canonical_nfse_key(self, issuer_document: str | None, number: str | None, verification: str | None) -> str | None:
        issuer = _digits(issuer_document)
        if not (issuer and number and verification):
            return None
        raw = f'{NFSE_KEY_PREFIX}:{issuer}:{number}:{verification}'
        return normalize_invoice_key(raw)

    def _add_common_warnings(self, data: InvoiceData) -> None:
        if not data.invoice_key:
            data.warnings.append('Chave da nota não identificada no XML.')
        if data.total_amount is None:
            data.warnings.append('Valor total não identificado no XML.')
        if not data.issuer_document:
            data.warnings.append('Documento do emitente/prestador não identificado no XML.')
