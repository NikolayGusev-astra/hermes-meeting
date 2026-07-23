import json

from docx import Document

from meeting_intelligence import cli


def _paragraphs(path):
    return [paragraph.text for paragraph in Document(path).paragraphs]


def test_write_summary_docx_includes_topics_and_timestamped_concepts(tmp_path):
    output = tmp_path / "summary.docx"

    cli.write_summary_docx(
        "Python lecture",
        "Ada",
        "45 min",
        ["Typing", "Testing"],
        output,
        [{"timestamp": "00:12", "concept": "Type hints"}],
    )

    assert _paragraphs(output) == [
        "Python lecture",
        "Speaker: Ada; Duration: 45 min",
        "Key topics",
        "Typing",
        "Testing",
        "Key concepts",
        "00:12: Type hints",
    ]


def test_generate_analytical_docx_from_json(tmp_path):
    source = tmp_path / "analysis.json"
    output = tmp_path / "analysis.docx"
    source.write_text(
        json.dumps({"Context": "Project is late.", "Recommendations": "Reduce scope."}),
        encoding="utf-8",
    )

    args = cli.argparse.Namespace(type="analytical", input=source, output=output)
    assert cli.cmd_generate_docx(args) == 0
    assert _paragraphs(output) == [
        "Analytical note",
        "Context",
        "Project is late.",
        "Recommendations",
        "Reduce scope.",
    ]


def test_generate_protocol_docx_from_json_with_review_warning(tmp_path):
    source = tmp_path / "protocol.json"
    output = tmp_path / "protocol.docx"
    source.write_text(
        json.dumps(
            {
                "participants": [{"name": "Ada"}],
                "decisions": [{"text": "Ship"}],
                "quality": {"status": "needs_review"},
            }
        ),
        encoding="utf-8",
    )

    args = cli.argparse.Namespace(type="protocol", input=source, output=output)
    assert cli.cmd_generate_docx(args) == 0
    assert output.is_file()


def test_agent_transcript_docx_converts_markdown_input(tmp_path, capsys):
    source = tmp_path / "notes.md"
    output = tmp_path / "notes.docx"
    source.write_text("# Notes\n\n[00:00] SPEAKER_00 | Hello", encoding="utf-8")

    args = cli.argparse.Namespace(transcript=source, docx=True, output=output)
    assert cli.cmd_agent_transcript(args) == 0
    capsys.readouterr()
    assert _paragraphs(output) == ["notes", "# Notes", "[00:00] SPEAKER_00 | Hello"]
