"""Small synthetic fixtures, never production candidate data."""

import io
import zipfile
from xml.sax.saxutils import escape

SAMPLE = [
    "TEST ONLY Synthetic Candidate",
    "Professional Summary",
    "I build Python workflow prototypes.",
    "Skills",
    "Python, Postgres, JavaScript",
    "Experience",
    "Software Engineer | TEST ONLY Labs | 2020-01-01 - Present | Built Python APIs",
    "Education",
    "Bachelor of Science | TEST ONLY University | 2018 - 2022 | In progress",
    "Certifications",
    "TEST ONLY Cloud Certificate | TEST ONLY Issuer | 2024 | expiry unknown | REF-TEST",
    "Projects",
    "TEST ONLY Workflow | Python prototype | Built a demo",
    "Languages",
    "English: working proficiency",
]


def pdf(lines=None, pages=1, password=None, image=False):
    from pypdf import PdfWriter
    from pypdf.generic import (
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
        NumberObject,
    )

    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        if lines is not None or not image:
            stream = DecodedStreamObject()
            escaped = [
                (line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)"))
                for line in (SAMPLE if lines is None else lines)
            ]
            stream.set_data(
                (
                    "BT /F1 11 Tf 20 770 Td 14 TL "
                    + " ".join(f"({line}) Tj T*" for line in escaped)
                    + " ET"
                ).encode()
            )
            page[NameObject("/Contents")] = writer._add_object(stream)
        if image:
            img = DecodedStreamObject()
            img.set_data(b"\x00\x00\x00")
            img.update(
                {
                    NameObject("/Type"): NameObject("/XObject"),
                    NameObject("/Subtype"): NameObject("/Image"),
                    NameObject("/Width"): NumberObject(1),
                    NameObject("/Height"): NumberObject(1),
                    NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
                    NameObject("/BitsPerComponent"): NumberObject(8),
                }
            )
            page["/Resources"][NameObject("/XObject")] = DictionaryObject(
                {NameObject("/Im0"): writer._add_object(img)}
            )
    if password:
        writer.encrypt(password)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def docx(lines=None, table=True, extra=None):
    paragraphs = [
        f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>"
        for line in (SAMPLE if lines is None else lines)
    ]
    if table and paragraphs:
        paragraphs[-1] = "<w:tbl><w:tr><w:tc>" + paragraphs[-1] + "</w:tc></w:tr></w:tbl>"
    document = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        + "".join(paragraphs)
        + "</w:body></w:document>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        archive.writestr("word/document.xml", document)
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return output.getvalue()
