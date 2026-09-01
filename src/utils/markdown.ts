// Pure markdown helper functions extracted from the former Dashboard.tsx.
// These perform string-only transformations (no JSX) and are consumed by
// MarkdownRenderer and the useProjectState hook.
import { UserStory, PRDSection } from '../components/types';

type SectionSource = {
  content?: unknown;
  markdown?: unknown;
  title?: unknown;
  name?: unknown;
};

export function getSafeSectionContent(content: unknown): string {
  if (content === null || content === undefined) return "";
  if (typeof content === 'string') return content;
  if (typeof content === 'object') {
    const source = content as SectionSource;
    if (source.content !== undefined) return getSafeSectionContent(source.content);
    if (source.markdown !== undefined) return getSafeSectionContent(source.markdown);
    try {
      return Object.entries(source as Record<string, unknown>)
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

export function getSafeSectionTitle(title: unknown): string {
  if (title === null || title === undefined) return "Untitled Section";
  if (typeof title === 'string') return title;
  if (typeof title === 'object') {
    const source = title as SectionSource;
    if (source.title !== undefined) return getSafeSectionTitle(source.title);
    if (source.name !== undefined) return getSafeSectionTitle(source.name);
    return JSON.stringify(title);
  }
  return String(title);
}

export function parsePRDToSections(markdown: unknown): PRDSection[] {
  if (!markdown) return [];
  const safeMarkdown = getSafeSectionContent(markdown);
  
  const sections: PRDSection[] = [];
  const lines = safeMarkdown.split('\n');
  
  let currentSectionId = 'title';
  let currentSectionTitle = 'Product Requirement Document';
  let currentContent: string[] = [];
  
  for (const line of lines) {
    const trimmed = line.trim();
    // Template sections use level-2/level-3 headings ("### Stakeholders",
    // "### 1. Business & Strategic Overview"), so treat BOTH as section
    // boundaries — otherwise the template's front-matter tables collapse into
    // one giant undifferentiated block.
    const isH3Boundary = trimmed.startsWith('### ');
    if (trimmed.startsWith('## ') || isH3Boundary) {
      // Save previous section if it has content
      sections.push({
        id: currentSectionId,
        title: currentSectionTitle,
        content: currentContent.join('\n').trim()
      });
      
      // Start new section
      const title = trimmed.replace(/^#{2,3}\s+/, '').trim();
      currentSectionTitle = title;
      
      // Determine ID from title
      if (title.toLowerCase().includes('executive summary')) {
        currentSectionId = 'exec_summary';
      } else if (title.toLowerCase().includes('technical architecture') || title.toLowerCase().includes('technical infrastructure') || title.toLowerCase().includes('technical constraints')) {
        currentSectionId = 'tech_arch';
      } else if (title.toLowerCase().includes('scope of requirements') || title.toLowerCase().includes('user stories')) {
        currentSectionId = 'user_stories';
      } else if (title.toLowerCase().includes('stakeholder')) {
        currentSectionId = 'stakeholders';
      } else if (title.toLowerCase().includes('version history')) {
        currentSectionId = 'version_history';
      } else if (title.toLowerCase().includes('review')) {
        currentSectionId = 'reviews';
      } else if (title.toLowerCase().includes('contents')) {
        currentSectionId = 'contents';
      } else if (title.toLowerCase().includes('business & strategic')) {
        currentSectionId = 'business_overview';
      } else if (title.toLowerCase().includes('product scope') || title.toLowerCase().includes('functional requirement')) {
        currentSectionId = 'product_scope';
      } else if (title.toLowerCase().includes('technical & operational')) {
        currentSectionId = 'tech_ops';
      } else if (title.toLowerCase().includes('appendix')) {
        currentSectionId = 'appendix';
      } else {
        currentSectionId =
          title
            .toLowerCase()
            .replace(/\*/g, '')
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, '') || 'section';
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

