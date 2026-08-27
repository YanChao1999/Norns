import { describe, expect, it } from 'vitest';

import { folderName, githubRepoFromUrl, repoChipLabel } from './workspaceLabel';

describe('workspaceLabel', () => {
  it('reads owner/repo from GitHub URLs', () => {
    expect(githubRepoFromUrl('https://github.com/acme/app.git')).toBe('acme/app');
    expect(githubRepoFromUrl('git@github.com:acme/app.git')).toBe('acme/app');
  });

  it('uses the folder name when there is no remote', () => {
    expect(folderName('/home/you/my-repo')).toBe('my-repo');
    expect(repoChipLabel('/home/you/my-repo', '')).toBe('my-repo');
  });

  it('prefers the GitHub name on the chip', () => {
    expect(repoChipLabel('/tmp/checkout', 'https://github.com/acme/app')).toBe('acme/app');
    expect(repoChipLabel('', '')).toBe('No git repo');
  });
});
