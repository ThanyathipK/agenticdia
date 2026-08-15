// DOCX & PDF export module (DocxExporter) extracted from the former Dashboard.tsx.
// Pure functions that accept a context object so they can be reused by the
// useProjectState hook without being coupled to component state.
import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel
} from 'docx';
import { handleError } from '../components/Toast';
import { UserStory } from '../components/types';
import { convertMarkdownToHtml } from './markdown';

export interface DocxExportContext {
  projectId: string | null;
  projectName: string;
  epicName: string;
  userStories: UserStory[];
  currentVersion: number;
  prdMarkdown: string;
  setSyncStatus: (msg: string) => void;
}

export function parseInlineFormatting(text: string): TextRun[] {
  if (!text) return [new TextRun({ text: "" })];
  const runs: TextRun[] = [];
  const tokens = text.split(/(\*\*.*?\*\*|`.*?`)/g);
  for (const token of tokens) {
    if (!token) continue;
    if (token.startsWith('**') && token.endsWith('**') && token.length > 4) {
      runs.push(new TextRun({ text: token.slice(2, -2), bold: true }));
    } else if (token.startsWith('`') && token.endsWith('`') && token.length > 2) {
      runs.push(new TextRun({
        text: token.slice(1, -1),
        font: "Consolas",
        size: 20,
        shading: { fill: "F1F5F9" }
      }));
    } else {
      runs.push(new TextRun({ text: token }));
    }
  }
  return runs.length > 0 ? runs : [new TextRun({ text })];
}

export function convertMarkdownToDocxParagraphs(md: string): Paragraph[] {
  if (!md) return [];
  const lines = md.split('\n');
  const paragraphs: Paragraph[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    if (trimmed.startsWith('# ')) {
      paragraphs.push(new Paragraph({
        text: trimmed.slice(2),
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 240, after: 120 }
      }));
    } else if (trimmed.startsWith('## ')) {
      paragraphs.push(new Paragraph({
        text: trimmed.slice(3),
        heading: HeadingLevel.HEADING_2,
        spacing: { before: 200, after: 100 }
      }));
    } else if (trimmed.startsWith('### ')) {
      paragraphs.push(new Paragraph({
        text: trimmed.slice(4),
        heading: HeadingLevel.HEADING_3,
        spacing: { before: 160, after: 80 }
      }));
    } else if (trimmed.startsWith('#### ')) {
      paragraphs.push(new Paragraph({
        text: trimmed.slice(5),
        heading: HeadingLevel.HEADING_4,
        spacing: { before: 120, after: 60 }
      }));
    } else if (trimmed.startsWith('> ')) {
      paragraphs.push(new Paragraph({
        children: parseInlineFormatting(trimmed.slice(2)),
        indent: { left: 720 },
        spacing: { before: 120, after: 120 }
      }));
    } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      paragraphs.push(new Paragraph({
        children: parseInlineFormatting(trimmed.slice(2)),
        bullet: { level: 0 },
        spacing: { before: 40, after: 40 }
      }));
    } else if (trimmed.match(/^\d+\.\s/)) {
      const content = trimmed.replace(/^\d+\.\s/, '');
      paragraphs.push(new Paragraph({
        children: parseInlineFormatting(content),
        bullet: { level: 0 },
        spacing: { before: 40, after: 40 }
      }));
    } else {
      paragraphs.push(new Paragraph({
        children: parseInlineFormatting(trimmed),
        spacing: { before: 60, after: 60 }
      }));
    }
  }

  return paragraphs;
}

export async function downloadDocx(ctx: DocxExportContext) {
  const { projectId, projectName, epicName, userStories, currentVersion, prdMarkdown, setSyncStatus } = ctx;
  setSyncStatus("Generating valid Office Open XML (.docx) document...");
  try {
    const docChildren: Paragraph[] = [];

    // Header & Project Metadata
    docChildren.push(
      new Paragraph({
        children: [
          new TextRun({
            text: "ENTERPRISE REQUIREMENTS SPECIFICATION",
            bold: true,
            size: 18,
            color: "8A6A50",
          }),
        ],
        spacing: { after: 100 },
      }),
      new Paragraph({
        children: [
          new TextRun({
            text: projectName,
            bold: true,
            size: 36,
            color: "0F172A",
          }),
        ],
        spacing: { after: 120 },
      }),
      new Paragraph({
        children: [
          new TextRun({ text: "Epic: ", bold: true, size: 20 }),
          new TextRun({ text: epicName, size: 20 }),
          new TextRun({ text: "   |   Version: ", bold: true, size: 20 }),
          new TextRun({ text: `v${currentVersion}.0`, size: 20 }),
          new TextRun({ text: "   |   Project ID: ", bold: true, size: 20 }),
          new TextRun({ text: projectId || "N/A", size: 20 }),
        ],
        spacing: { after: 240 },
      })
    );

    // Section 1: Project & Epic Details
    docChildren.push(
      new Paragraph({
        text: "1. Project & Epic Details",
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 240, after: 120 },
      }),
      new Paragraph({
        children: [
          new TextRun({ text: "Project Name: ", bold: true }),
          new TextRun({ text: projectName }),
        ],
        spacing: { after: 80 },
      }),
      new Paragraph({
        children: [
          new TextRun({ text: "Epic Name: ", bold: true }),
          new TextRun({ text: epicName }),
        ],
        spacing: { after: 80 },
      }),
      new Paragraph({
        children: [
          new TextRun({ text: "Document Version: ", bold: true }),
          new TextRun({ text: `V${currentVersion}.0` }),
        ],
        spacing: { after: 160 },
      })
    );

    // Section 2: User Stories & Acceptance Criteria
    docChildren.push(
      new Paragraph({
        text: "2. Scope of Requirements & User Stories",
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 240, after: 120 },
      })
    );

    if (userStories.length > 0) {
      userStories.forEach((us) => {
        docChildren.push(
          new Paragraph({
            text: `${us.ticket_code}: ${us.story_title}`,
            heading: HeadingLevel.HEADING_2,
            spacing: { before: 180, after: 80 },
          }),
          new Paragraph({
            children: [
              new TextRun({ text: "As a ", bold: true, color: "0F172A" }),
              new TextRun({ text: us.as_a }),
            ],
          }),
          new Paragraph({
            children: [
              new TextRun({ text: "I want to ", bold: true, color: "0F172A" }),
              new TextRun({ text: us.i_want_to }),
            ],
            spacing: { after: 40 },
          }),
          new Paragraph({
            children: [
              new TextRun({ text: "So that ", bold: true, color: "0F172A" }),
              new TextRun({ text: us.so_that }),
            ],
            spacing: { after: 80 },
          })
        );

        if (us.acceptance_criteria && us.acceptance_criteria.length > 0) {
          docChildren.push(
            new Paragraph({
              children: [
                new TextRun({ text: "Acceptance Criteria:", bold: true, color: "1E293B" }),
              ],
              spacing: { before: 80, after: 40 },
            })
          );
          us.acceptance_criteria.forEach((ac) => {
            docChildren.push(
              new Paragraph({
                children: parseInlineFormatting(ac),
                bullet: { level: 0 },
                spacing: { before: 20, after: 20 },
              })
            );
          });
        }
      });
    } else {
      docChildren.push(
        new Paragraph({
          text: "No user stories registered.",
          spacing: { after: 120 },
        })
      );
    }

    // Section 3: Product Requirement Document (PRD)
    docChildren.push(
      new Paragraph({
        text: "3. Product Requirement Document (PRD)",
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 280, after: 120 },
      })
    );

    if (prdMarkdown) {
      const prdParagraphs = convertMarkdownToDocxParagraphs(prdMarkdown);
      docChildren.push(...prdParagraphs);
    }

    const doc = new Document({
      sections: [
        {
          properties: {
            page: {
              margin: {
                top: 1440,
                right: 1440,
                bottom: 1440,
                left: 1440,
              },
            },
          },
          children: docChildren,
        },
      ],
    });

    const blob = await Packer.toBlob(doc);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `PRD-${projectId || "export"}-V${currentVersion}.docx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setSyncStatus("PRD Word Document (.docx) downloaded.");
  } catch (err) {
    handleError("Failed to generate the DOCX document.", err);
    setSyncStatus("Failed to generate DOCX document.");
  }
}

export function printPDF(ctx: DocxExportContext) {
  const { projectId, epicName, currentVersion, prdMarkdown, setSyncStatus } = ctx;
  setSyncStatus("Generating isolated PDF printable frame...");
  
  // Convert current Markdown to styled HTML string
  const formattedHtml = convertMarkdownToHtml(prdMarkdown);
  
  // Create a temporary hidden iframe to hold the pristine document print content
  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.right = '0';
  iframe.style.bottom = '0';
  iframe.style.width = '0';
  iframe.style.height = '0';
  iframe.style.border = 'none';
  document.body.appendChild(iframe);
  
  const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
  if (!iframeDoc) {
    // Fallback
    window.print();
    return;
  }
  
  // Write high-fidelity print template to iframe document
  const printTemplate = `
    <!DOCTYPE html>
    <html>
    <head>
      <title>${epicName || "Product Requirement Document"}</title>
      <link rel="preconnect" href="https://fonts.googleapis.com">
      <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
      <style>
        @page {
          size: A4 portrait;
          margin: 20mm;
        }
        body {
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          font-size: 10pt;
          line-height: 1.6;
          color: #1e293b;
          background: #ffffff;
          margin: 0;
          padding: 0;
        }
        .header-cover {
          border-bottom: 2px solid #8a6a50;
          padding-bottom: 16px;
          margin-bottom: 28px;
        }
        .header-tag {
          font-size: 8.5pt;
          color: #8a6a50;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          font-weight: 700;
          margin-bottom: 4px;
        }
        h1 {
          font-size: 22pt;
          font-weight: 800;
          color: #0f172a;
          margin: 0 0 8px 0;
          letter-spacing: -0.025em;
          line-height: 1.25;
        }
        .meta-info {
          color: #64748b;
          font-size: 9pt;
        }
        h2 {
          font-size: 15pt;
          font-weight: 700;
          color: #0f172a;
          margin-top: 28px;
          margin-bottom: 10px;
          border-bottom: 1px solid #e2e8f0;
          padding-bottom: 4px;
          page-break-after: avoid;
          break-after: avoid;
        }
        h3 {
          font-size: 11.5pt;
          font-weight: 600;
          color: #1e293b;
          margin-top: 20px;
          margin-bottom: 8px;
          page-break-after: avoid;
          break-after: avoid;
        }
        p {
          margin-top: 0;
          margin-bottom: 10px;
        }
        ul, ol {
          margin-top: 0;
          margin-bottom: 14px;
          padding-left: 20px;
        }
        li {
          margin-bottom: 5px;
        }
        blockquote {
          margin: 14px 0;
          padding: 10px 14px;
          background-color: #f8fafc;
          border-left: 4px solid #8a6a50;
          border-radius: 0 6px 6px 0;
          font-style: italic;
          color: #475569;
        }
        strong {
          font-weight: 700;
          color: #0f172a;
        }
        code {
          font-family: 'JetBrains Mono', monospace;
          font-size: 8.5pt;
          background-color: #f1f5f9;
          color: #8a6a50;
          padding: 2px 4px;
          border-radius: 3px;
          border: 1px solid #e2e8f0;
        }
        .footer-layout {
          margin-top: 40px;
          border-top: 1px solid #e2e8f0;
          padding-top: 10px;
          font-size: 8pt;
          color: #94a3b8;
          display: flex;
          justify-content: space-between;
        }
      </style>
    </head>
    <body>
      <div class="header-cover">
        <div class="header-tag">Enterprise Requirements Specification</div>
        <h1>${epicName || "PromptPay Merchant Settlement Engine"}</h1>
        <div class="meta-info">
          Project: ${projectId} &bull; Document Version: V${currentVersion}.0 &bull; Compilation Date: ${new Date().toLocaleDateString()}
        </div>
      </div>
      
      <div class="content-body">
        ${formattedHtml}
      </div>

      <div class="footer-layout">
        <div>Compiled via Krungsri Nimble Requirements Engine</div>
        <div>Page 1 of 1</div>
      </div>
    </body>
    </html>
  `;
  
  iframeDoc.open();
  iframeDoc.write(printTemplate);
  iframeDoc.close();
  
  // Trigger print window with slight delay to ensure browser engine processes CSS and web fonts
  setTimeout(() => {
    if (iframe.contentWindow) {
      iframe.contentWindow.focus();
      iframe.contentWindow.print();
    }
    // Remove iframe from DOM after print dialog handles it
    setTimeout(() => {
      document.body.removeChild(iframe);
      setSyncStatus('Document PDF exported.');
    }, 1500);
  }, 600);
}
