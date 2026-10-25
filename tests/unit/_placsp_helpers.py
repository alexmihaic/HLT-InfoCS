"""Constructores de XML 100 % sintético para las pruebas del canal 643. Sin red ni datos reales."""

from __future__ import annotations

FEED_URL = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom"
PAGE2_URL = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3_20261023_202231.atom"
PAGE3_URL = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3_20261022_201500.atom"
ENTRY_ID_PREFIX = "https://contrataciondelestado.es/sindicacion/licitacionesPerfilContratante/"

NAMESPACES = (
    'xmlns="http://www.w3.org/2005/Atom" '
    'xmlns:at="http://purl.org/atompub/tombstones/1.0" '
    'xmlns:cbc="urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2" '
    'xmlns:cac="urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2" '
    'xmlns:ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2" '
    'xmlns:bext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2"'
)


def entry_xml(
    key: str = "SYN-9001",
    *,
    updated: str = "2026-10-24T12:00:00.000+02:00",
    folder: str | None = "SYN/9001",
    platform: str | None = "9990000009001",
    dir3: str | None = None,
    status: str | None = None,
    nuts: str | None = None,
    cpv: str | None = None,
    deadline: str | None = None,
    notices: tuple[tuple[str | None, str | None], ...] = (),
    title: str | None = None,
    extra_status: str = "",
    atom_id: str | None = None,
) -> str:
    identifiers = ""
    if platform is not None:
        identifiers += f'<cac:PartyIdentification><cbc:ID schemeName="ID_PLATAFORMA">{platform}</cbc:ID></cac:PartyIdentification>'
    if dir3 is not None:
        identifiers += f'<cac:PartyIdentification><cbc:ID schemeName="DIR3">{dir3}</cbc:ID></cac:PartyIdentification>'
    project = ""
    if cpv is not None:
        project += f"<cac:RequiredCommodityClassification><cbc:ItemClassificationCode>{cpv}</cbc:ItemClassificationCode></cac:RequiredCommodityClassification>"
    if nuts is not None:
        project += f"<cac:RealizedLocation><cbc:CountrySubentityCode>{nuts}</cbc:CountrySubentityCode></cac:RealizedLocation>"
    process = ""
    if deadline is not None:
        process = f"<cac:TenderingProcess><cac:TenderSubmissionDeadlinePeriod><cbc:EndDate>{deadline}</cbc:EndDate></cac:TenderSubmissionDeadlinePeriod></cac:TenderingProcess>"
    notice_xml = ""
    for notice_type, issue in notices:
        notice_xml += "<ext:ValidNoticeInfo>"
        if notice_type is not None:
            notice_xml += f"<bext:NoticeTypeCode>{notice_type}</bext:NoticeTypeCode>"
        if issue is not None:
            notice_xml += f"<bext:NoticeIssueDate>{issue}</bext:NoticeIssueDate>"
        notice_xml += "</ext:ValidNoticeInfo>"
    return (
        "<entry>"
        + (f"<id>{atom_id if atom_id is not None else ENTRY_ID_PREFIX + key}</id>")
        + (f"<title>{title}</title>" if title is not None else "")
        + f"<updated>{updated}</updated>"
        + "<ext:ContractFolderStatus>"
        + (f"<cbc:ContractFolderID>{folder}</cbc:ContractFolderID>" if folder is not None else "")
        + (f"<bext:ContractFolderStatusCode>{status}</bext:ContractFolderStatusCode>" if status is not None else "")
        + f"<ext:LocatedContractingParty><cac:Party>{identifiers}</cac:Party></ext:LocatedContractingParty>"
        + (f"<cac:ProcurementProject>{project}</cac:ProcurementProject>" if project else "")
        + process
        + notice_xml
        + extra_status
        + "</ext:ContractFolderStatus></entry>"
    )


def tombstone_xml(key: str, kind: str | None = "ANULADA", when: str = "2026-10-23T20:27:20.747+02:00") -> str:
    comment = f'<at:comment type="{kind}"/>' if kind is not None else ""
    return f'<at:deleted-entry ref="{ENTRY_ID_PREFIX}{key}" when="{when}">{comment}</at:deleted-entry>'


def feed_xml(
    entries: str = "",
    *,
    tombstones: str = "",
    next_url: str | None = PAGE2_URL,
    extra_links: str = "",
    root_attrs: str = "",
    feed_updated: str = "2026-10-24T20:02:56.368+02:00",
    prolog: str = '<?xml version="1.0" encoding="UTF-8"?>',
) -> bytes:
    link = f'<link href="{next_url}" rel="next"/>' if next_url else ""
    text = (
        f"{prolog}<feed {NAMESPACES} {root_attrs}>"
        f"<id>{FEED_URL}</id><updated>{feed_updated}</updated>{link}{extra_links}{tombstones}{entries}</feed>"
    )
    return text.encode("utf-8")
