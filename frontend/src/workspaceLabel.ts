export function githubRepoFromUrl(url: string): string {
  const text = url.trim().replace(/\.git$/, '');
  if (!text) {
    return '';
  }
  const match = text.match(/github\.com[:/]([^/]+)\/([^/#?]+)/i);
  if (match) {
    return `${match[1]}/${match[2]}`;
  }
  if (/^[^/]+\/[^/]+$/.test(text)) {
    return text;
  }
  return '';
}

export function folderName(path: string): string {
  const parts = path.trim().replace(/\/+$/, '').split('/').filter(Boolean);
  return parts[parts.length - 1] || '';
}

export function repoChipLabel(path?: string, gitUrl?: string): string {
  return githubRepoFromUrl(gitUrl || '') || folderName(path || '') || 'No git repo';
}
