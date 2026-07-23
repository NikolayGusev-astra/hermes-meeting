from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


W, H = 1200, 900
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "pipeline-infographic.png"
FONT = Path(r"C:\Windows\Fonts\segoeui.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\segoeuib.ttf")

BG = "#0B1220"
PANEL = "#111C2F"
PANEL_2 = "#14233A"
STROKE = "#2A3D5C"
TEXT = "#F2F7FF"
MUTED = "#9AAFC8"
CYAN = "#38BDF8"
VIOLET = "#A78BFA"
GREEN = "#34D399"
AMBER = "#FBBF24"
PINK = "#FB7185"


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def text_center(box, value, size, color=TEXT, bold=False, spacing=3):
    f = font(size, bold)
    bounds = d.multiline_textbbox((0, 0), value, font=f, spacing=spacing, align="center")
    x = box[0] + (box[2] - box[0] - (bounds[2] - bounds[0])) / 2
    y = box[1] + (box[3] - box[1] - (bounds[3] - bounds[1])) / 2 - bounds[1]
    d.multiline_text((x, y), value, font=f, fill=color, spacing=spacing, align="center")


def round_box(box, fill=PANEL, outline=STROKE, radius=18, width=2):
    d.rounded_rectangle(box, radius, fill=fill, outline=outline, width=width)


def arrow(start, end, color=CYAN, width=4):
    d.line((start, end), fill=color, width=width)
    x1, y1 = start
    x2, y2 = end
    if abs(x2 - x1) >= abs(y2 - y1):
        sign = 1 if x2 > x1 else -1
        points = [(x2, y2), (x2 - 12 * sign, y2 - 7), (x2 - 12 * sign, y2 + 7)]
    else:
        sign = 1 if y2 > y1 else -1
        points = [(x2, y2), (x2 - 7, y2 - 12 * sign), (x2 + 7, y2 - 12 * sign)]
    d.polygon(points, fill=color)


def label(x, y, value, color):
    f = font(12, True)
    bb = d.textbbox((0, 0), value, font=f)
    d.rounded_rectangle((x, y, x + bb[2] - bb[0] + 20, y + 27), 13, fill=color)
    d.text((x + 10, y + 5), value, font=f, fill=BG)


# Subtle background structure.
for x in range(30, W, 60):
    d.line((x, 118, x, 728), fill="#0E1A2B", width=1)
for y in range(140, 730, 48):
    d.line((30, y, W - 30, y), fill="#0E1A2B", width=1)

# Header.
d.rounded_rectangle((50, 43, 58, 100), 4, fill=CYAN)
d.text((78, 42), "Meeting Intelligence Pipeline", font=font(34, True), fill=TEXT)
d.text((80, 86), "From raw conversations to verified, actionable meeting outcomes", font=font(16), fill=MUTED)
d.line((50, 128, 1150, 128), fill=STROKE, width=2)

# Input sources group.
input_box = (42, 182, 294, 552)
round_box(input_box, PANEL, STROKE, 20)
label(62, 162, "01  INPUT", CYAN)
text_center((62, 198, 274, 231), "Input Sources", 21, TEXT, True)
d.text((86, 234), "Bring the meeting from anywhere", font=font(12), fill=MUTED)

sources = [("FILE", "▣"), ("URL", "↗"), ("TELEGRAM", "✈"), ("EMAIL", "✉"), ("CHAT", "●"), ("TRANSCRIPT", "≡")]
for i, (name, icon) in enumerate(sources):
    col, row = i % 2, i // 2
    x = 62 + col * 108
    y = 274 + row * 82
    d.rounded_rectangle((x, y, x + 94, y + 62), 12, fill="#172840", outline="#284664", width=1)
    d.ellipse((x + 11, y + 18, x + 31, y + 38), fill="#1D4561")
    text_center((x + 11, y + 17, x + 31, y + 39), icon, 12, CYAN, True)
    text_center((x + 5, y + 40, x + 89, y + 58), name, 10 if name != "TRANSCRIPT" else 9, TEXT, True)

# Main pipeline arrows behind nodes.
arrow((294, 367), (332, 367))
arrow((512, 367), (552, 367), VIOLET)
arrow((822, 367), (862, 367), GREEN)

# Transcription.
trans_box = (332, 268, 512, 466)
round_box(trans_box, PANEL_2, "#315276", 20)
label(349, 248, "02  PROCESS", VIOLET)
d.ellipse((389, 300, 455, 366), fill="#372B63")
text_center((389, 300, 455, 366), "W", 31, VIOLET, True)
text_center((350, 380, 494, 410), "Transcription", 19, TEXT, True)
text_center((351, 417, 493, 449), "Whisper\n+ GPU auto", 14, MUTED, False)

# Agent analysis.
agent_box = (552, 220, 822, 514)
round_box(agent_box, PANEL_2, "#4B3977", 20)
label(573, 200, "03  REASON", VIOLET)
text_center((573, 240, 801, 272), "Agent Analysis", 21, TEXT, True)
d.text((595, 277), "A deliberate three-phase pass", font=font(12), fill=MUTED)
phases = [("01", "Participants", "Identify speakers & roles", CYAN), ("02", "Extract", "Decisions, tasks & risks", VIOLET), ("03", "Verify", "Check facts & ownership", GREEN)]
for i, (num, title, sub, color) in enumerate(phases):
    y = 311 + i * 60
    d.rounded_rectangle((573, y, 801, y + 48), 12, fill="#192942", outline="#304A6B", width=1)
    d.rounded_rectangle((584, y + 10, 618, y + 38), 8, fill=color)
    text_center((584, y + 10, 618, y + 38), num, 11, BG, True)
    d.text((632, y + 8), title, font=font(14, True), fill=TEXT)
    d.text((632, y + 26), sub, font=font(10), fill=MUTED)

# Output.
output_box = (862, 268, 1060, 466)
round_box(output_box, "#112B31", "#2B6B69", 20)
label(880, 248, "04  DELIVER", GREEN)
text_center((880, 294, 1042, 326), "Output", 20, TEXT, True)
for y, name, color in [(344, "PROTOCOL JSON", CYAN), (396, "DOCX", GREEN)]:
    d.rounded_rectangle((884, y, 1038, y + 38), 10, fill="#163A40", outline="#2D666A", width=1)
    d.rounded_rectangle((895, y + 10, 913, y + 28), 5, fill=color)
    d.text((924, y + 10), name, font=font(12, True), fill=TEXT)

# Optional branch / MCP.
arrow((961, 466), (961, 534), AMBER, 3)
mcp_box = (775, 534, 1148, 691)
round_box(mcp_box, "#211D2D", "#5D4B36", 20)
label(796, 514, "OPTIONAL  •  OPT-IN", AMBER)
d.text((798, 555), "MCP integrations", font=font(19, True), fill=TEXT)
d.text((798, 582), "Send verified outcomes where work happens", font=font(12), fill=MUTED)
for i, name in enumerate(["Jira", "Confluence", "Email", "Calendar"]):
    x = 797 + (i % 2) * 166
    y = 613 + (i // 2) * 39
    d.rounded_rectangle((x, y, x + 147, y + 30), 9, fill="#2A2535", outline="#554835", width=1)
    d.ellipse((x + 10, y + 9, x + 22, y + 21), fill=AMBER)
    d.text((x + 31, y + 7), name, font=font(11, True), fill=TEXT)

# GPU auto-detect bar.
gpu = (42, 758, 1148, 840)
round_box(gpu, "#0E2631", "#28556B", 18)
d.rounded_rectangle((62, 778, 106, 820), 12, fill="#154454")
text_center((62, 778, 106, 820), "GPU", 13, CYAN, True)
d.text((126, 775), "GPU auto-detect", font=font(17, True), fill=TEXT)
d.text((126, 802), "Uses accelerated Whisper when a compatible GPU is available; gracefully falls back to CPU.", font=font(12), fill=MUTED)
d.rounded_rectangle((942, 784, 1126, 814), 15, fill="#123C46", outline="#287080", width=1)
d.ellipse((955, 793, 967, 805), fill=GREEN)
d.text((979, 790), "AUTO SELECT", font=font(11, True), fill="#B8F3E0")

# Footer.
d.text((50, 863), "MEETING INTELLIGENCE  /  TRUSTED BY DESIGN", font=font(11, True), fill="#647C9D")
d.text((940, 863), "INPUT → INSIGHT → ACTION", font=font(11, True), fill="#647C9D")

img.save(OUT, "PNG", optimize=True)
print(OUT)
