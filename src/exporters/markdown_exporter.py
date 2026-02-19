from ..core.document import Document

class MarkdownExporter:
    @staticmethod
    def export(document: Document) -> str:
        md = f"# {document.filename}\n\n"
        for page in document.pages:
            md += f"## Page {page.page_num}\n\n"
            md += page.text + "\n\n"
            for table in page.tables:
                md += "### Table\n"
                for row in table.data:
                    md += "| " + " | ".join(row) + " |\n"
                md += "\n"
        return md