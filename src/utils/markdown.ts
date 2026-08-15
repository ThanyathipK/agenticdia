// Pure markdown helper functions extracted from the former Dashboard.tsx.
// These perform string-only transformations (no JSX) and are consumed by
// MarkdownRenderer, DocxExporter and the useProjectState hook.
import { UserStory, PRDSection } from '../components/types';

export function convertMarkdownToHtml(md: string): string {
  if (!md) return '';
  const lines = md.split('\n');
  let html = '';
  let inList = false;
  let inNumList = false;

  for (let line of lines) {
    const trimmed = line.trim();

    // Close list tags if no longer in a list context
    if (inList && !trimmed.startsWith('- ') && !trimmed.startsWith('* ')) {
      html += '</ul>\n';
      inList = false;
    }
    if (inNumList && !trimmed.match(/^\d+\.\s/)) {
      html += '</ol>\n';
      inNumList = false;
    }

    // Headers
    if (trimmed.startsWith('# ')) {
      html += `<h1 style="color: #0f172a; font-family: 'Segoe UI', Arial, sans-serif; font-size: 22pt; margin-top: 24pt; margin-bottom: 12pt; border-bottom: 2px solid #8a6a50; padding-bottom: 6px; font-weight: 800;">${trimmed.slice(2)}</h1>\n`;
      continue;
    }
    if (trimmed.startsWith('## ')) {
      html += `<h2 style="color: #1e293b; font-family: 'Segoe UI', Arial, sans-serif; font-size: 16pt; margin-top: 18pt; margin-bottom: 9pt; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; font-weight: 700;">${trimmed.slice(3)}</h2>\n`;
      continue;
    }
    if (trimmed.startsWith('### ')) {
      html += `<h3 style="color: #334155; font-family: 'Segoe UI', Arial, sans-serif; font-size: 13pt; margin-top: 14pt; margin-bottom: 6pt; font-weight: 600;">${trimmed.slice(4)}</h3>\n`;
      continue;
    }
    if (trimmed.startsWith('#### ')) {
      html += `<h4 style="color: #475569; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt; margin-top: 12pt; margin-bottom: 6pt; font-weight: 600;">${trimmed.slice(5)}</h4>\n`;
      continue;
    }

    // Blockquotes
    if (trimmed.startsWith('> ')) {
      html += `<blockquote style="border-left: 4px solid #8a6a50; background-color: #f8fafc; padding: 10px 15px; margin: 15px 0; color: #475569; font-style: italic; border-radius: 0 4px 4px 0;">${trimmed.slice(2)}</blockquote>\n`;
      continue;
    }

    // Horizontal Rules
    if (trimmed === '---' || trimmed === '***') {
      html += '<hr style="border: 0; border-top: 1px solid #cbd5e1; margin: 20px 0;" />\n';
      continue;
    }

    // Bullet Lists
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      if (!inList) {
        html += '<ul style="margin-top: 6pt; margin-bottom: 6pt; padding-left: 20pt; list-style-type: disc;">\n';
        inList = true;
      }
      html += `<li style="color: #334155; font-family: 'Segoe UI', Arial, sans-serif; font-size: 10.5pt; margin-bottom: 4pt; line-height: 1.5;">${trimmed.slice(2)}</li>\n`;
      continue;
    }

    // Numbered Lists
    const numListMatch = trimmed.match(/^(\d+)\.\s(.*)/);
    if (numListMatch) {
      if (!inNumList) {
        html += '<ol style="margin-top: 6pt; margin-bottom: 6pt; padding-left: 20pt; list-style-type: decimal;">\n';
        inNumList = true;
      }
      html += `<li style="color: #334155; font-family: 'Segoe UI', Arial, sans-serif; font-size: 10.5pt; margin-bottom: 4pt; line-height: 1.5;">${numListMatch[2]}</li>\n`;
      continue;
    }

    // Empty line
    if (trimmed === '') {
      html += '<p style="margin: 0; height: 10pt;"></p>\n';
      continue;
    }

    // Paragraph
    html += `<p style="color: #334155; font-family: 'Segoe UI', Arial, sans-serif; font-size: 10.5pt; line-height: 1.6; margin-top: 0; margin-bottom: 10pt;">${trimmed}</p>\n`;
  }

  // Close any unclosed list items
  if (inList) html += '</ul>\n';
  if (inNumList) html += '</ol>\n';

  // Apply inline formatting to completed html segments
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong style="font-weight: 700; color: #0f172a;">$1</strong>');
  html = html.replace(/`(.*?)`/g, '<code style="background-color: #f1f5f9; color: #8a6a50; font-family: Consolas, Monaco, monospace; padding: 2px 4px; border-radius: 3px; font-size: 9.5pt; border: 1px solid #e2e8f0;">$1</code>');

  return html;
}

export function getSafeSectionContent(content: any): string {
  if (content === null || content === undefined) return "";
  if (typeof content === 'string') return content;
  if (typeof content === 'object') {
    if (content.content !== undefined) return getSafeSectionContent(content.content);
    if (content.markdown !== undefined) return getSafeSectionContent(content.markdown);
    
    try {
      return Object.entries(content)
        .map(([key, val]) => {
          const valStr = typeof val === 'object' ? JSON.stringify(val) : String(val);
          return `**${key}:** ${valStr}`;
        })
        .join('\n\n');
    } catch (e) {
      return JSON.stringify(content);
    }
  }
  return String(content);
}

export function getSafeSectionTitle(title: any): string {
  if (title === null || title === undefined) return "Untitled Section";
  if (typeof title === 'string') return title;
  if (typeof title === 'object') {
    if (title.title !== undefined) return getSafeSectionTitle(title.title);
    if (title.name !== undefined) return getSafeSectionTitle(title.name);
    return JSON.stringify(title);
  }
  return String(title);
}

export function parsePRDToSections(markdown: any): PRDSection[] {
  if (!markdown) return [];
  const safeMarkdown = getSafeSectionContent(markdown);
  
  const sections: PRDSection[] = [];
  const lines = safeMarkdown.split('\n');
  
  let currentSectionId = 'title';
  let currentSectionTitle = 'Product Requirement Document';
  let currentContent: string[] = [];
  
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('## ')) {
      // Save previous section if it has content
      sections.push({
        id: currentSectionId,
        title: currentSectionTitle,
        content: currentContent.join('\n').trim()
      });
      
      // Start new section
      const title = trimmed.slice(3).trim();
      currentSectionTitle = title;
      
      // Determine ID from title
      if (title.toLowerCase().includes('executive summary')) {
        currentSectionId = 'exec_summary';
      } else if (title.toLowerCase().includes('technical architecture') || title.toLowerCase().includes('technical infrastructure') || title.toLowerCase().includes('technical constraints')) {
        currentSectionId = 'tech_arch';
      } else if (title.toLowerCase().includes('scope of requirements') || title.toLowerCase().includes('user stories')) {
        currentSectionId = 'user_stories';
      } else {
        currentSectionId = title.toLowerCase().replace(/[^a-z0-9]+/g, '_');
      }
      currentContent = [line];
    } else {
      currentContent.push(line);
    }
  }
  
  // Save last section
  sections.push({
    id: currentSectionId,
    title: currentSectionTitle,
    content: currentContent.join('\n').trim()
  });
  
  return sections.filter(s => s.content !== '' || s.id === 'title');
}

export function stitchSectionsToPRD(sectionsList: PRDSection[]): string {
  return sectionsList.map(s => s.content).join('\n\n');
}

export function formatUserStoriesToMarkdown(userStories: UserStory[]): string {
  let md = `## 3. Scope of Requirements (User Stories)\n`;
  if (!userStories || userStories.length === 0) {
    md += `No user stories registered yet.`;
    return md;
  }
  
  userStories.forEach(us => {
    md += `\n### ${us.ticket_code}: ${us.story_title}\n`;
    md += `**As a** ${us.as_a}\n`;
    md += `**I want to** ${us.i_want_to}\n`;
    md += `**So that** ${us.so_that}\n\n`;
    
    if (us.acceptance_criteria && us.acceptance_criteria.length > 0) {
      md += `**Acceptance Criteria:**\n`;
      us.acceptance_criteria.forEach(ac => {
        md += `- ${ac}\n`;
      });
    }
  });
  
  return md;
}

