import markdown
from xhtml2pdf import pisa

# Read Markdown
with open('Agrovision_Report.md', 'r', encoding='utf-8') as f:
    text = f.read()

# Convert Markdown to HTML
html_content = markdown.markdown(text)

# Add some basic CSS styling for the PDF
html_template = f"""
<html>
<head>
<style>
    @page {{
        size: a4 portrait;
        margin: 2cm;
    }}
    body {{
        font-family: Arial, sans-serif;
        color: #333;
        line-height: 1.6;
    }}
    h1 {{
        color: #2c3e50;
        border-bottom: 2px solid #3498db;
        padding-bottom: 5px;
    }}
    h2 {{
        color: #2980b9;
        margin-top: 20px;
    }}
    h3 {{
        color: #16a085;
    }}
    p {{
        margin-bottom: 10px;
    }}
    li {{
        margin-bottom: 5px;
    }}
</style>
</head>
<body>
{html_content}
</body>
</html>
"""

# Write to PDF
with open('Agrovision_Report.pdf', 'wb') as result_file:
    pisa_status = pisa.CreatePDF(html_template, dest=result_file)

if pisa_status.err:
    print("Error generating PDF")
else:
    print("Successfully generated Agrovision_Report.pdf!")
