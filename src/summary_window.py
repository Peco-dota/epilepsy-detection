import webbrowser
import tempfile
import os

class SummaryWindow:
    def __init__(self):
        pass
        
    def show_summary(self, summary_text, ai_analysis=None, filepath=None):
        """Zobrazí súhrn session v prehliadači"""
        # Vytvor HTML súbor
        html_content = self._generate_html(summary_text, ai_analysis, filepath)
        
        # Ulož do dočasného súboru
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', encoding='utf-8') as f:
            f.write(html_content)
            html_path = f.name
        
        # Otvor v prehliadači
        webbrowser.open('file://' + html_path)
        print(f"\n✓ Súhrn otvorený v prehliadači")
        print(f"📄 HTML súbor: {html_path}")
        
    def _generate_html(self, summary_text, ai_analysis, filepath):
        """Generuje HTML obsah pre súhrn"""
        ai_section = ""
        if ai_analysis:
            # Konvertuj plain text na HTML s riadkami
            ai_html = ai_analysis.replace('\n', '<br>')
            ai_section = f"""
            <div class="section ai-section">
                <h2>🤖 AI Analýza</h2>
                <div class="ai-content">
                    {ai_html}
                </div>
            </div>
            """
        
        stats_html = summary_text.replace('\n', '<br>')
        
        file_section = ""
        if filepath:
            file_section = f"""
            <div class="file-info">
                📁 Dáta uložené: <code>{filepath}</code>
            </div>
            """
        
        html = f"""
<!DOCTYPE html>
<html lang="sk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Súhrn Monitorovacej Session</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px 20px;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #0066cc 0%, #004999 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 10px;
        }}
        
        .header p {{
            font-size: 16px;
            opacity: 0.9;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .section {{
            background: #f8f9fa;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
            border-left: 5px solid #0066cc;
        }}
        
        .ai-section {{
            border-left-color: #28a745;
        }}
        
        .section h2 {{
            font-size: 24px;
            margin-bottom: 20px;
            color: #333;
        }}
        
        .ai-content {{
            font-size: 16px;
            line-height: 1.8;
            color: #444;
            white-space: pre-wrap;
        }}
        
        .stats-content {{
            font-family: 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.6;
            color: #555;
            background: white;
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
        }}
        
        .file-info {{
            text-align: center;
            padding: 20px;
            background: #e9ecef;
            border-radius: 8px;
            font-size: 14px;
            color: #666;
        }}
        
        .file-info code {{
            background: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            color: #0066cc;
        }}
        
        .footer {{
            text-align: center;
            padding: 30px;
            color: #999;
            font-size: 14px;
        }}
        
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            
            .container {{
                box-shadow: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Súhrn Monitorovacej Session</h1>
            <p>Prehľad dát a AI analýza</p>
        </div>
        
        <div class="content">
            {ai_section}
            
            <div class="section">
                <h2>📈 Štatistické Dáta</h2>
                <div class="stats-content">
                    {stats_html}
                </div>
            </div>
            
            {file_section}
        </div>
        
        <div class="footer">
            Child Emotion Detection System © 2025
        </div>
    </div>
</body>
</html>
"""
        return html


