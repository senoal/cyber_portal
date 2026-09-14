"""Professional PDF export for the BlackOwl organization structure."""

from io import BytesIO
import os

from PIL import Image as PilImage, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _person(value, fallback):
    value = {"name": value} if isinstance(value, str) else (value or {})
    return {"name": value.get("name") or fallback, "photo": value.get("photo") or "", "certifications": value.get("certifications") or []}


def _fonts():
    regular, bold = "Helvetica", "Helvetica-Bold"
    try:
        pdfmetrics.registerFont(TTFont("SegoeUI", r"C:\Windows\Fonts\segoeui.ttf"))
        pdfmetrics.registerFont(TTFont("SegoeUIBold", r"C:\Windows\Fonts\segoeuib.ttf"))
        regular, bold = "SegoeUI", "SegoeUIBold"
    except Exception:
        pass
    return regular, bold


def _avatar(person, root, size=120):
    image = None
    if person["photo"].startswith("/static/"):
        path = os.path.join(root, "static", person["photo"][8:].replace("/", os.sep))
        if os.path.isfile(path):
            try:
                image = PilImage.open(path).convert("RGBA")
            except OSError:
                pass
    if image is None:
        image = PilImage.new("RGBA", (size, size), "#243447")
        initials = "".join(part[0] for part in person["name"].split()[:2]).upper() or "?"
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 42)
        except OSError:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), initials, font=font)
        draw.text(((size-(bbox[2]-bbox[0]))/2, (size-(bbox[3]-bbox[1]))/2), initials, fill="#f4c84a", font=font)
    image.thumbnail((size, size))
    fitted = PilImage.new("RGBA", (size, size), "#1a2430")
    fitted.paste(image, ((size-image.width)//2, (size-image.height)//2), image if image.mode == "RGBA" else None)
    mask = PilImage.new("L", (size, size), 0); ImageDraw.Draw(mask).ellipse((7, 7, size-7, size-7), fill=255)
    result = PilImage.new("RGBA", (size, size), (0, 0, 0, 0)); result.paste(fitted, (0, 0), mask)
    ImageDraw.Draw(result).ellipse((3, 3, size-4, size-4), outline="#f4c84a", width=4)
    stream = BytesIO(); result.save(stream, "PNG"); stream.seek(0)
    return Image(stream, width=27*mm, height=27*mm)


def build_blackowl_organization_pdf(structure, root_dir):
    regular, bold = _fonts(); output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("OrgTitle", parent=styles["Title"], fontName=bold, fontSize=25, leading=30, textColor=colors.HexColor("#17212e"), spaceAfter=3)
    heading = ParagraphStyle("Heading", parent=styles["Heading2"], fontName=bold, fontSize=13, leading=17, textColor=colors.HexColor("#bd8500"), spaceBefore=12, spaceAfter=7)
    role = ParagraphStyle("Role", parent=styles["Normal"], fontName=bold, fontSize=8, leading=10, textColor=colors.HexColor("#bd8500"))
    name = ParagraphStyle("Name", parent=styles["Normal"], fontName=bold, fontSize=12, leading=15, textColor=colors.HexColor("#17212e"))
    body = ParagraphStyle("Body", parent=styles["Normal"], fontName=regular, fontSize=9, leading=12, textColor=colors.HexColor("#4b5d70"))
    story = [Paragraph("BLACKOWL ORGANIZATION", role), Paragraph("IT Security Department", title), Paragraph("Organization structure, personnel profiles, and certifications.", body), Spacer(1, 7*mm)]
    def card(value, role_name):
        person = _person(value, role_name); certs = ", ".join(person["certifications"]) or "No certifications listed"
        details = [Paragraph(role_name.upper(), role), Paragraph(person["name"], name), Paragraph(f"<b>Certifications:</b> {certs}", body)]
        table = Table([[_avatar(person, root_dir), details]], colWidths=[34*mm, 146*mm])
        table.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("BOX",(0,0),(-1,-1),.65,colors.HexColor("#cbd5df")),("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f8fafc")),("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8)])); return table
    story += [Paragraph("Department Head", heading), card(structure.get("head"), "Department Head"), Spacer(1,6*mm), Paragraph("Teams", heading)]
    for team in structure.get("teams", []):
        story.append(Paragraph(team.get("name", "Unnamed Team"), ParagraphStyle("Team", parent=heading, spaceBefore=9)))
        if team.get("lead"): story.append(card(team["lead"], "Team Lead"))
        for member in team.get("members", []): story += [Spacer(1,3*mm), card(member, "Team Member")]
    doc.build(story); output.seek(0); return output
