/** Slug `owner/repo` para exibição, ou "—" se não houver URL GitHub válida com repositório. */
export function parseGithubRepoDisplaySlug(url: string | null): string {
  const raw = (url ?? "").trim();
  if (!raw) return "—";
  try {
    const u = raw.replace(/\.git$/, "").split("?")[0];
    const m = u.match(/github\.com\/([^/]+)\/([^/]+)/i);
    if (m) return `${m[1]}/${m[2]}`;
  } catch {
    /* ignore */
  }
  return "—";
}

/** URL não vazia, aponta para github.com e inclui organização/repositório. */
export function hasLinkedGithubRepo(project: { github_repo_url: string | null }): boolean {
  const raw = (project.github_repo_url ?? "").trim();
  if (!raw) return false;
  if (!raw.toLowerCase().includes("github.com")) return false;
  return parseGithubRepoDisplaySlug(project.github_repo_url) !== "—";
}
