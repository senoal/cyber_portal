import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file
)

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle
)
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak,
    KeepTogether
)

from app.models.va_model import (
    get_dashboard_summary,
    get_risk_distribution,
    get_vulnerability_trend,
    get_vulnerability_by_asset_type,
    get_top5_asset_risk_score,
    get_top5_critical_vulnerability,
    get_vulnerability_severity_by_asset
)


# ==========================================================
# BLUEPRINT
# ==========================================================

pdf_bp = Blueprint(
    "pdf_bp",
    __name__,
    url_prefix="/pdf"
)


# ==========================================================
# LOGIN CHECK
# ==========================================================

def login_required():

    return "user" in session


# ==========================================================
# PDF COLOR PALETTE
# ==========================================================

COLOR_PRIMARY = colors.HexColor("#F4C84A")

COLOR_DARK = colors.HexColor("#111827")
COLOR_DARKER = colors.HexColor("#0B1220")

COLOR_TEXT = colors.HexColor("#1F2937")
COLOR_MUTED = colors.HexColor("#64748B")

COLOR_BORDER = colors.HexColor("#D9DEE7")
COLOR_LIGHT = colors.HexColor("#F5F7FA")
COLOR_LIGHTER = colors.HexColor("#FAFBFC")

COLOR_CRITICAL = colors.HexColor("#FF4D4F")
COLOR_HIGH = colors.HexColor("#FF8C00")
COLOR_MEDIUM = colors.HexColor("#FFD700")
COLOR_LOW = colors.HexColor("#52C41A")
COLOR_INFO = colors.HexColor("#69B1FF")


# ==========================================================
# FORMAT DATE
# ==========================================================

def format_date(value):

    if not value:
        return "-"

    try:

        if hasattr(value, "strftime"):

            return value.strftime(
                "%d-%m-%Y"
            )

        value = str(value)

        if len(value) >= 10:

            return datetime.strptime(
                value[:10],
                "%Y-%m-%d"
            ).strftime(
                "%d-%m-%Y"
            )

    except Exception:

        pass

    return str(value)


# ==========================================================
# PDF STYLES
# ==========================================================

def create_styles():

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=25,
            textColor=COLOR_DARK,
            alignment=TA_CENTER,
            spaceAfter=7
        )
    )

    styles.add(
        ParagraphStyle(
            name="CoverSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=COLOR_MUTED,
            alignment=TA_CENTER,
            spaceAfter=20
        )
    )

    styles.add(
        ParagraphStyle(
            name="SectionTitle",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=COLOR_DARK,
            spaceBefore=0,
            spaceAfter=9
        )
    )

    styles.add(
        ParagraphStyle(
            name="Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=COLOR_TEXT
        )
    )

    styles.add(
        ParagraphStyle(
            name="Caption",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.8,
            leading=10.5,
            textColor=COLOR_MUTED,
            spaceBefore=4,
            spaceAfter=8
        )
    )

    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=COLOR_MUTED
        )
    )

    styles.add(
        ParagraphStyle(
            name="KPIValue",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=16,
            textColor=COLOR_DARK,
            alignment=TA_CENTER
        )
    )

    styles.add(
        ParagraphStyle(
            name="KPIHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9,
            textColor=colors.white,
            alignment=TA_CENTER
        )
    )

    return styles


# ==========================================================
# FILTER
# ==========================================================

def get_filters():

    return {

        "date_from":
            request.args.get(
                "date_from",
                ""
            ).strip(),

        "date_to":
            request.args.get(
                "date_to",
                ""
            ).strip(),

        "asset_type":
            request.args.get(
                "asset_type",
                ""
            ).strip(),

        "risk_level":
            request.args.get(
                "risk_level",
                ""
            ).strip()

    }


# ==========================================================
# MATPLOTLIB IMAGE
# ==========================================================

def fig_to_image(
    fig,
    width_mm,
    height_mm
):

    buffer = io.BytesIO()

    fig.savefig(
        buffer,
        format="png",
        dpi=170,
        bbox_inches="tight",
        facecolor="white"
    )

    plt.close(fig)

    buffer.seek(0)

    return Image(
        buffer,
        width=width_mm * mm,
        height=height_mm * mm
    )


# ==========================================================
# RISK DISTRIBUTION
# ==========================================================

def create_risk_chart(data):

    # ------------------------------------------------------
    # DATA
    # ------------------------------------------------------

    values = [
        data.get("High", 0),
        data.get("Medium", 0),
        data.get("Low", 0)
    ]

    labels = [
        "High",
        "Medium",
        "Low"
    ]

    chart_colors = [
        "#FF4D4F",
        "#FFD700",
        "#52C41A"
    ]

    total = sum(values)

    # ------------------------------------------------------
    # FIGURE
    # ------------------------------------------------------

    fig = plt.figure(
        figsize=(7.2, 2.5),
        dpi=120,
        facecolor="white"
    )

    # ------------------------------------------------------
    # DONUT
    # ------------------------------------------------------

    ax = fig.add_axes([
        0.04,
        0.08,
        0.42,
        0.82
    ])

    ax.set_aspect("equal")

    if total == 0:

        ax.text(
            0.5,
            0.5,
            "No Data",
            ha="center",
            va="center",
            fontsize=10,
            color="#64748B",
            fontweight="bold"
        )

        ax.axis("off")

    else:

        ax.pie(

            values,

            colors=chart_colors,

            startangle=90,

            counterclock=False,

            radius=0.95,

            wedgeprops={
                "width": 0.34,
                "edgecolor": "white",
                "linewidth": 1.2
            }

        )

        # --------------------------------------------------
        # CENTER VALUE
        # --------------------------------------------------

        ax.text(
            0,
            0.06,
            str(total),
            ha="center",
            va="center",
            fontsize=17,
            fontweight="bold",
            color="#1F2937"
        )

        ax.text(
            0,
            -0.17,
            "Assets",
            ha="center",
            va="center",
            fontsize=7.5,
            color="#64748B"
        )

        ax.axis("off")

    # ------------------------------------------------------
    # LEGEND
    # ------------------------------------------------------

    legend_ax = fig.add_axes([
        0.53,
        0.10,
        0.42,
        0.78
    ])

    legend_ax.set_xlim(0, 1)
    legend_ax.set_ylim(0, 1)
    legend_ax.axis("off")

    if total > 0:

        y_positions = [
            0.72,
            0.50,
            0.28
        ]

        for index, (
            label,
            value,
            color
        ) in enumerate(
            zip(
                labels,
                values,
                chart_colors
            )
        ):

            percentage = (
                value / total
            ) * 100

            y = y_positions[index]

            # ----------------------------------------------
            # COLOR DOT
            # ----------------------------------------------

            legend_ax.scatter(
                0.04,
                y,
                s=45,
                color=color,
                marker="o"
            )

            # ----------------------------------------------
            # LABEL
            # ----------------------------------------------

            legend_ax.text(
                0.12,
                y + 0.025,
                label,
                fontsize=8.5,
                fontweight="bold",
                color="#1F2937",
                va="center"
            )

            # ----------------------------------------------
            # VALUE
            # ----------------------------------------------

            legend_ax.text(
                0.12,
                y - 0.065,
                f"{value} asset",
                fontsize=7.2,
                color="#64748B",
                va="center"
            )

            # ----------------------------------------------
            # PERCENTAGE
            # ----------------------------------------------

            legend_ax.text(
                0.90,
                y,
                f"{percentage:.1f}%",
                fontsize=8.5,
                fontweight="bold",
                color="#1F2937",
                ha="right",
                va="center"
            )

    # ------------------------------------------------------
    # IMPORTANT
    # ------------------------------------------------------
    # Jangan menggunakan:
    #
    # bbox_inches="tight"
    #
    # karena dapat menghasilkan bounding box
    # yang sangat besar pada layout add_axes().
    # ------------------------------------------------------

    return fig_to_image(
        fig,
        170,
        55
    )


# ==========================================================
# VULNERABILITY TREND
# ==========================================================

def create_trend_chart(data):

    fig, ax = plt.subplots(
        figsize=(8.0, 3.0),
        dpi=170
    )

    labels = [

        format_date(
            item["scan_date"]
        )

        for item in data

    ]

    values = [

        item["total"] or 0

        for item in data

    ]

    if not values:

        ax.text(
            0.5,
            0.5,
            "No data",
            ha="center",
            va="center",
            fontsize=11
        )

        ax.axis("off")

    else:

        x = range(
            len(values)
        )

        ax.plot(

            x,

            values,

            color="#E5B900",

            linewidth=2.2,

            marker="o",

            markersize=4

        )

        ax.fill_between(

            x,

            values,

            alpha=0.08,

            color="#FFD700"

        )

        ax.set_xticks(x)

        ax.set_xticklabels(

            labels,

            rotation=40,

            ha="right",

            fontsize=7

        )

        ax.tick_params(
            axis="y",
            labelsize=7
        )

        ax.set_ylabel(

            "Total Vulnerability",

            fontsize=7

        )

        ax.set_title(

            "Vulnerability Trend",

            fontsize=11,

            fontweight="bold",

            loc="left",

            pad=8

        )

        ax.grid(

            axis="y",

            alpha=0.18,

            linewidth=0.7

        )

        ax.spines[
            "top"
        ].set_visible(False)

        ax.spines[
            "right"
        ].set_visible(False)

    fig.tight_layout()

    return fig_to_image(
        fig,
        170,
        60
    )


# ==========================================================
# ASSET TYPE
# ==========================================================

def create_asset_type_chart(data):

    fig, ax = plt.subplots(
        figsize=(8.0, 3.2),
        dpi=170
    )

    labels = [

        item["asset_type"]

        for item in data

    ]

    values = [

        item["total"] or 0

        for item in data

    ]

    if not values:

        ax.text(
            0.5,
            0.5,
            "No data",
            ha="center",
            va="center",
            fontsize=11
        )

        ax.axis("off")

    else:

        bars = ax.bar(

            labels,

            values,

            color="#FFD700",

            width=0.55

        )

        ax.set_title(

            "Vulnerability by Asset Type",

            fontsize=11,

            fontweight="bold",

            loc="left",

            pad=8

        )

        ax.set_ylabel(

            "Total Vulnerability",

            fontsize=7

        )

        ax.tick_params(
            axis="x",
            labelsize=8
        )

        ax.tick_params(
            axis="y",
            labelsize=7
        )

        ax.grid(

            axis="y",

            alpha=0.18,

            linewidth=0.7

        )

        ax.spines[
            "top"
        ].set_visible(False)

        ax.spines[
            "right"
        ].set_visible(False)

        for bar, value in zip(
            bars,
            values
        ):

            ax.text(

                bar.get_x()
                + bar.get_width() / 2,

                value + 0.8,

                str(value),

                ha="center",

                va="bottom",

                fontsize=8,

                fontweight="bold"

            )

    fig.tight_layout()

    return fig_to_image(
        fig,
        170,
        68
    )


# ==========================================================
# SEVERITY BY ASSET
# ==========================================================

def create_severity_chart(data):

    fig, ax = plt.subplots(
        figsize=(8.0, 4.0),
        dpi=170
    )

    reversed_data = list(
        reversed(data)
    )

    labels = [

        item["asset"]

        for item in reversed_data

    ]

    critical = [

        item["critical"] or 0

        for item in reversed_data

    ]

    high = [

        item["high"] or 0

        for item in reversed_data

    ]

    medium = [

        item["medium"] or 0

        for item in reversed_data

    ]

    low = [

        item["low"] or 0

        for item in reversed_data

    ]

    info = [

        item["info"] or 0

        for item in reversed_data

    ]

    if not data:

        ax.text(
            0.5,
            0.5,
            "No data",
            ha="center",
            va="center",
            fontsize=11
        )

        ax.axis("off")

    else:

        y = range(
            len(labels)
        )

        ax.barh(

            y,

            critical,

            color="#FF4D4F",

            label="Critical"

        )

        ax.barh(

            y,

            high,

            left=critical,

            color="#FF8C00",

            label="High"

        )

        left_medium = [

            c + h

            for c, h in zip(
                critical,
                high
            )

        ]

        ax.barh(

            y,

            medium,

            left=left_medium,

            color="#FFD700",

            label="Medium"

        )

        left_low = [

            c + h + m

            for c, h, m in zip(
                critical,
                high,
                medium
            )

        ]

        ax.barh(

            y,

            low,

            left=left_low,

            color="#52C41A",

            label="Low"

        )

        left_info = [

            c + h + m + l

            for c, h, m, l in zip(
                critical,
                high,
                medium,
                low
            )

        ]

        ax.barh(

            y,

            info,

            left=left_info,

            color="#69B1FF",

            label="Info"

        )

        ax.set_yticks(
            list(y)
        )

        ax.set_yticklabels(

            labels,

            fontsize=8

        )

        ax.tick_params(
            axis="x",
            labelsize=7
        )

        ax.set_title(

            "Vulnerability Severity by Asset",

            fontsize=11,

            fontweight="bold",

            loc="left",

            pad=10

        )

        ax.legend(

            loc="upper center",

            bbox_to_anchor=(
                0.5,
                1.06
            ),

            ncol=5,

            frameon=False,

            fontsize=7

        )

        ax.grid(

            axis="x",

            alpha=0.18,

            linewidth=0.7

        )

        ax.spines[
            "top"
        ].set_visible(False)

        ax.spines[
            "right"
        ].set_visible(False

        )

    fig.tight_layout()

    return fig_to_image(
        fig,
        170,
        82
    )


# ==========================================================
# TABLE STYLE
# ==========================================================

def apply_table_style(
    table,
    header_background=COLOR_DARK
):

    table.setStyle(

        TableStyle([

            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                header_background
            ),

            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),

            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold"
            ),

            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                7.8
            ),

            (
                "FONTNAME",
                (0, 1),
                (-1, -1),
                "Helvetica"
            ),

            (
                "TEXTCOLOR",
                (0, 1),
                (-1, -1),
                COLOR_TEXT
            ),

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.35,
                COLOR_BORDER
            ),

            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [
                    colors.white,
                    COLOR_LIGHT
                ]
            ),

            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE"
            ),

            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                6
            ),

            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                6
            ),

            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                7
            ),

            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                7
            )

        ])

    )


# ==========================================================
# PAGE HEADER / FOOTER
# ==========================================================

def pdf_header_footer(
    canvas,
    doc
):

    canvas.saveState()

    width, height = A4

    # --------------------------------------
    # TOP LINE
    # --------------------------------------

    canvas.setStrokeColor(
        COLOR_PRIMARY
    )

    canvas.setLineWidth(
        1.2
    )

    canvas.line(

        18 * mm,

        height - 13 * mm,

        width - 18 * mm,

        height - 13 * mm

    )

    # --------------------------------------
    # HEADER
    # --------------------------------------

    canvas.setFont(
        "Helvetica-Bold",
        7.5
    )

    canvas.setFillColor(
        COLOR_DARK
    )

    canvas.drawString(

        18 * mm,

        height - 10 * mm,

        "IT SECURITY"

    )

    canvas.setFont(
        "Helvetica",
        7
    )

    canvas.setFillColor(
        COLOR_MUTED
    )

    canvas.drawRightString(

        width - 18 * mm,

        height - 10 * mm,

        "Vulnerability Assessment Report"

    )

    # --------------------------------------
    # FOOTER LINE
    # --------------------------------------

    canvas.setStrokeColor(
        COLOR_BORDER
    )

    canvas.setLineWidth(
        0.5
    )

    canvas.line(

        18 * mm,

        14 * mm,

        width - 18 * mm,

        14 * mm

    )

    # --------------------------------------
    # FOOTER TEXT
    # --------------------------------------

    canvas.setFont(
        "Helvetica",
        7
    )

    canvas.setFillColor(
        COLOR_MUTED
    )

    canvas.drawString(

        18 * mm,

        8.5 * mm,

        "IT Security Department"

    )

    canvas.drawRightString(

        width - 18 * mm,

        8.5 * mm,

        f"Page {doc.page}"

    )

    canvas.restoreState()


# ==========================================================
# PDF REPORT
# ==========================================================

@pdf_bp.route(
    "/va-report",
    methods=["GET"]
)
def va_report():

    # ======================================================
    # AUTHORIZATION
    # ======================================================

    if not login_required():

        return redirect(
            url_for(
                "auth.login"
            )
        )

    if session.get(
        "level"
    ) != "Internal":

        return redirect(
            url_for(
                "user.dashboard"
            )
        )

    # ======================================================
    # FILTER
    # ======================================================

    filters = get_filters()

    date_from = (
        filters["date_from"]
        or None
    )

    date_to = (
        filters["date_to"]
        or None
    )

    asset_type = (
        filters["asset_type"]
        or None
    )

    risk_level = (
        filters["risk_level"]
        or None
    )

    # ======================================================
    # DASHBOARD DATA
    # ======================================================

    summary = get_dashboard_summary(

        date_from=date_from,

        date_to=date_to,

        asset_type=asset_type,

        risk_level=risk_level

    )

    risk_distribution = get_risk_distribution(

        date_from=date_from,

        date_to=date_to,

        asset_type=asset_type,

        risk_level=risk_level

    )

    trend_data = get_vulnerability_trend(

        date_from=date_from,

        date_to=date_to,

        asset_type=asset_type,

        risk_level=risk_level

    )

    asset_chart = get_vulnerability_by_asset_type(

        date_from=date_from,

        date_to=date_to,

        asset_type=asset_type,

        risk_level=risk_level

    )

    top5_risk_asset = get_top5_asset_risk_score(

        date_from=date_from,

        date_to=date_to,

        asset_type=asset_type,

        risk_level=risk_level

    )

    top5_critical_asset = get_top5_critical_vulnerability(

        date_from=date_from,

        date_to=date_to,

        asset_type=asset_type,

        risk_level=risk_level

    )

    severity_chart = get_vulnerability_severity_by_asset(

        date_from=date_from,

        date_to=date_to,

        asset_type=asset_type,

        risk_level=risk_level

    )

    # ======================================================
    # PDF DOCUMENT
    # ======================================================

    pdf_buffer = io.BytesIO()

    doc = SimpleDocTemplate(

        pdf_buffer,

        pagesize=A4,

        rightMargin=18 * mm,

        leftMargin=18 * mm,

        topMargin=21 * mm,

        bottomMargin=18 * mm,

        title=(
            "IT Security - Analisis dan "
            "Reporting Vulnerability Assessment"
        ),

        author="IT Security Department"

    )

    styles = create_styles()

    story = []

    # ======================================================
    # PAGE 1
    # COVER / PARAMETERS
    # ======================================================

    story.append(
        Spacer(
            1,
            18 * mm
        )
    )

    story.append(

        Paragraph(

            "IT Security - Analisis dan Reporting<br/>"
            "Vulnerability Assessment",

            styles["CoverTitle"]

        )

    )

    story.append(

        Paragraph(

            "Application Security",

            styles["CoverSubtitle"]

        )

    )

    # Gold separator

    separator = Table(
        [[""]],
        colWidths=[
            170 * mm
        ],
        rowHeights=[
            1.2 * mm
        ]
    )

    separator.setStyle(

        TableStyle([

            (
                "BACKGROUND",
                (0, 0),
                (-1, -1),
                COLOR_PRIMARY
            )

        ])

    )

    story.append(
        separator
    )

    story.append(
        Spacer(
            1,
            14 * mm
        )
    )

    story.append(

        Paragraph(

            "REPORT PARAMETERS",

            styles["SectionTitle"]

        )

    )

    filter_data = [

        [
            "Parameter",
            "Value"
        ],

        [
            "Start Date",
            format_date(date_from)
            if date_from
            else "All"
        ],

        [
            "End Date",
            format_date(date_to)
            if date_to
            else "All"
        ],

        [
            "Asset Type",
            asset_type
            or "All"
        ],

        [
            "Risk Level",
            risk_level
            or "All"
        ],

        [
            "Generated",
            datetime.now().strftime(
                "%d-%m-%Y %H:%M"
            )
        ]

    ]

    filter_table = Table(

        filter_data,

        colWidths=[

            45 * mm,

            125 * mm

        ]

    )

    apply_table_style(
        filter_table
    )

    story.append(
        filter_table
    )

    story.append(
        Spacer(
            1,
            12 * mm
        )
    )

    story.append(

        Paragraph(

            "Report ini berisi analisis Vulnerability "
            "Assessment berdasarkan parameter filter "
            "yang digunakan pada VA Dashboard.",

            styles["Body"]

        )

    )

    story.append(
        Spacer(
            1,
            8 * mm
        )
    )

    story.append(

        Paragraph(

            "<b>Document Purpose</b><br/>"
            "Memberikan ringkasan kondisi vulnerability "
            "untuk mendukung monitoring, analysis, dan "
            "penentuan prioritas remediation oleh IT Security.",

            styles["Body"]

        )

    )

    story.append(
        PageBreak()
    )

    # ======================================================
    # PAGE 2
    # EXECUTIVE SUMMARY + 2 CHARTS
    # ======================================================

    story.append(

        Paragraph(

            "1. Executive Summary",

            styles["SectionTitle"]

        )

    )

    summary_data = [

        [

            "Total Asset",

            "Total Vulnerability",

            "Critical",

            "High",

            "Medium",

            "Low"

        ],

        [

            str(
                summary["total_asset"]
            ),

            str(
                summary["total_vulnerability"]
            ),

            str(
                summary["critical"]
            ),

            str(
                summary["high"]
            ),

            str(
                summary["medium"]
            ),

            str(
                summary["low"]
            )

        ]

    ]

    summary_table = Table(

        summary_data,

        colWidths=[

            28 * mm,

            34 * mm,

            25 * mm,

            25 * mm,

            29 * mm,

            29 * mm

        ]

    )

    apply_table_style(
        summary_table
    )

    story.append(
        summary_table
    )

    story.append(
        Spacer(
            1,
            5 * mm
        )
    )

    story.append(

        Paragraph(

            "Executive summary menunjukkan jumlah asset "
            "dan vulnerability berdasarkan filter report "
            "yang dipilih.",

            styles["Caption"]

        )

    )

    # ------------------------------
    # Risk Distribution
    # ------------------------------

    story.append(

        Paragraph(

            "2. Risk Distribution",

            styles["SectionTitle"]

        )

    )

    story.append(

        create_risk_chart(
            risk_distribution
        )

    )

    story.append(

        Paragraph(

            "Keterangan: Risk Distribution menunjukkan "
            "proporsi asset berdasarkan Risk Level. "
            "Nilai persentase dihitung terhadap total "
            "asset yang masuk dalam filter report.",

            styles["Caption"]

        )

    )

    # ------------------------------
    # Trend
    # ------------------------------

    story.append(

        Paragraph(

            "3. Vulnerability Trend",

            styles["SectionTitle"]

        )

    )

    story.append(

        create_trend_chart(
            trend_data
        )

    )

    story.append(

        Paragraph(

            "Keterangan: grafik menunjukkan perubahan "
            "jumlah Total Vulnerability berdasarkan "
            "Scan Date.",

            styles["Caption"]

        )

    )

    story.append(
        PageBreak()
    )

    # ======================================================
    # PAGE 3
    # ASSET TYPE + TABLES
    # ======================================================

    story.append(

        Paragraph(

            "4. Vulnerability by Asset Type",

            styles["SectionTitle"]

        )

    )

    story.append(

        create_asset_type_chart(
            asset_chart
        )

    )

    story.append(

        Paragraph(

            "Keterangan: grafik menunjukkan distribusi "
            "vulnerability berdasarkan jenis asset.",

            styles["Caption"]

        )

    )

    # ======================================================
    # TOP 5 RISK
    # ======================================================

    story.append(

        Paragraph(

            "5. Top 5 Asset by Risk Score",

            styles["SectionTitle"]

        )

    )

    risk_table_data = [

        [

            "#",

            "Asset",

            "Source",

            "Risk Score",

            "Risk Level"

        ]

    ]

    for index, item in enumerate(

        top5_risk_asset,

        start=1

    ):

        risk_table_data.append(

            [

                str(index),

                str(item["asset"]),

                str(item["source"]),

                str(item["risk_score"]),

                str(item["risk_level"])

            ]

        )

    if len(
        risk_table_data
    ) == 1:

        risk_table_data.append(

            [

                "-",

                "No data",

                "-",

                "-",

                "-"

            ]

        )

    risk_table = Table(

        risk_table_data,

        colWidths=[

            10 * mm,

            48 * mm,

            62 * mm,

            25 * mm,

            25 * mm

        ],

        repeatRows=1

    )

    apply_table_style(
        risk_table
    )

    story.append(
        risk_table
    )

    story.append(

        Paragraph(

            "Keterangan: Risk Score dihitung berdasarkan "
            "bobot severity vulnerability. Asset dengan "
            "score lebih tinggi menjadi prioritas "
            "remediation yang lebih tinggi.",

            styles["Caption"]

        )

    )

    # ======================================================
    # TOP 5 CRITICAL
    # ======================================================

    story.append(

        Paragraph(

            "6. Top 5 Asset by Critical Vulnerability",

            styles["SectionTitle"]

        )

    )

    critical_table_data = [

        [

            "#",

            "Asset",

            "Critical",

            "High",

            "Risk Level"

        ]

    ]

    for index, item in enumerate(

        top5_critical_asset,

        start=1

    ):

        critical_table_data.append(

            [

                str(index),

                str(item["asset"]),

                str(item["critical"]),

                str(item["high"]),

                str(item["risk_level"])

            ]

        )

    if len(
        critical_table_data
    ) == 1:

        critical_table_data.append(

            [

                "-",

                "No data",

                "-",

                "-",

                "-"

            ]

        )

    critical_table = Table(

        critical_table_data,

        colWidths=[

            10 * mm,

            78 * mm,

            25 * mm,

            25 * mm,

            32 * mm

        ],

        repeatRows=1

    )

    apply_table_style(
        critical_table
    )

    story.append(
        critical_table
    )

    story.append(

        Paragraph(

            "Keterangan: tabel menampilkan asset dengan "
            "jumlah Critical Vulnerability tertinggi, "
            "kemudian mempertimbangkan High Vulnerability.",

            styles["Caption"]

        )

    )

    story.append(
        PageBreak()
    )

    # ======================================================
    # PAGE 4
    # SEVERITY + RISK INFORMATION
    # ======================================================

    story.append(

        Paragraph(

            "7. Vulnerability Severity by Asset",

            styles["SectionTitle"]

        )

    )

    story.append(

        create_severity_chart(
            severity_chart
        )

    )

    story.append(

        Paragraph(

            "Keterangan: stacked bar menunjukkan "
            "komposisi Critical, High, Medium, Low, "
            "dan Info pada setiap asset. Visualisasi "
            "dibatasi pada Top 5 asset sesuai logic "
            "dashboard.",

            styles["Caption"]

        )

    )

    story.append(
        Spacer(
            1,
            8 * mm
        )
    )

    # ======================================================
    # RISK SCORE INFORMATION
    # ======================================================

    story.append(

        Paragraph(

            "8. Risk Score Information",

            styles["SectionTitle"]

        )

    )

    risk_info_data = [

        [

            "Severity",

            "Weight"

        ],

        [

            "Critical",

            "10"

        ],

        [

            "High",

            "7"

        ],

        [

            "Medium",

            "4"

        ],

        [

            "Low",

            "2"

        ],

        [

            "Info",

            "1"

        ]

    ]

    risk_info_table = Table(

        risk_info_data,

        colWidths=[

            65 * mm,

            35 * mm

        ]

    )

    apply_table_style(
        risk_info_table
    )

    story.append(
        risk_info_table
    )

    story.append(
        Spacer(
            1,
            6 * mm
        )
    )

    story.append(

        Paragraph(

            "<b>Risk Score Formula</b><br/>"
            "Risk Score = "
            "(Critical × 10) + "
            "(High × 7) + "
            "(Medium × 4) + "
            "(Low × 2) + "
            "(Info × 1)",

            styles["Body"]

        )

    )

    story.append(
        Spacer(
            1,
            4 * mm
        )
    )

    story.append(

        Paragraph(

            "Semakin tinggi nilai Risk Score, semakin "
            "tinggi prioritas remediation.",

            styles["Body"]

        )

    )

    story.append(
        Spacer(
            1,
            18 * mm
        )
    )

    # ======================================================
    # MANAGEMENT NOTE
    # ======================================================

    management_note = Table(

        [

            [

                Paragraph(

                    "<b>Management Note</b><br/>"
                    "Gunakan hasil analisis ini sebagai "
                    "referensi untuk menentukan prioritas "
                    "remediation berdasarkan severity, "
                    "Risk Score, dan konsentrasi vulnerability "
                    "pada masing-masing asset.",

                    styles["Body"]

                )

            ]

        ],

        colWidths=[
            170 * mm
        ]

    )

    management_note.setStyle(

        TableStyle([

            (

                "BACKGROUND",

                (0, 0),

                (-1, -1),

                COLOR_LIGHT

            ),

            (

                "BOX",

                (0, 0),

                (-1, -1),

                0.5,

                COLOR_BORDER

            ),

            (

                "LEFTPADDING",

                (0, 0),

                (-1, -1),

                12

            ),

            (

                "RIGHTPADDING",

                (0, 0),

                (-1, -1),

                12

            ),

            (

                "TOPPADDING",

                (0, 0),

                (-1, -1),

                10

            ),

            (

                "BOTTOMPADDING",

                (0, 0),

                (-1, -1),

                10

            )

        ])

    )

    story.append(
        management_note
    )

    # ======================================================
    # BUILD
    # ======================================================

    doc.build(

        story,

        onFirstPage=pdf_header_footer,

        onLaterPages=pdf_header_footer

    )

    pdf_buffer.seek(0)

    filename = (

        "VA_Report_"

        + datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        + ".pdf"

    )

    return send_file(

        pdf_buffer,

        mimetype="application/pdf",

        as_attachment=True,

        download_name=filename

    )


# ==========================================================
# EXISTING PDF EDITOR
# ==========================================================

@pdf_bp.route("/")
def index():

    if not login_required():

        return redirect(
            url_for(
                "auth.login"
            )
        )

    return render_template(
        "internal/pdf_editor.html"
    )