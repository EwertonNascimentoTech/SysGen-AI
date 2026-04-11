/**
 * Formata nomes de ficheiros da wiki (slugs com hífens) para leitura em português.
 * Remove hífens, corrige acentuação comum e capitaliza palavras.
 */

const ACRONYMS: Record<string, string> = {
  jwt: "JWT",
  sso: "SSO",
  api: "API",
  ui: "UI",
  git: "Git",
  oauth: "OAuth",
  pdf: "PDF",
  crm: "CRM",
  erp: "ERP",
  sql: "SQL",
  nosql: "NoSQL",
  http: "HTTP",
  https: "HTTPS",
  url: "URL",
  xml: "XML",
  json: "JSON",
  yaml: "YAML",
  css: "CSS",
  html: "HTML",
  rest: "REST",
  grpc: "gRPC",
  readme: "README",
  bpmn: "BPMN",
  md: "MD",
  idigital: "iDigital",
  bootstrap: "Bootstrap",
  frontend: "Frontend",
  backend: "Backend",
};

/** Palavras frequentes em slugs de documentação (sem acentos) → forma correta */
const WORD_FIX: Record<string, string> = {
  servico: "serviço",
  servicos: "serviços",
  basico: "básico",
  publico: "público",
  tecnico: "técnico",
  rapidos: "rápidos",
  rapido: "rápido",
  logica: "lógica",
  analitico: "analítico",
  analytico: "analítico",
  checkin: "check-in",
  negocio: "negócio",
  negocios: "negócios",
  usuario: "usuário",
  usuarios: "usuários",
  gestao: "gestão",
  navegacao: "navegação",
  documentacao: "documentação",
  inicializacao: "inicialização",
  configuracao: "configuração",
  autenticacao: "autenticação",
  autorizacao: "autorização",
  validacao: "validação",
  utilizacao: "utilização",
  integracao: "integração",
  administracao: "administração",
  administrativo: "administrativo",
  implementacao: "implementação",
  especificacao: "especificação",
  comunicacao: "comunicação",
  visualizacao: "visualização",
  sincronizacao: "sincronização",
  importacao: "importação",
  exportacao: "exportação",
  atualizacao: "atualização",
  criacao: "criação",
  edicao: "edição",
  exclusao: "exclusão",
  inclusao: "inclusão",
  selecao: "seleção",
  execucao: "execução",
  transacao: "transação",
  notificacao: "notificação",
  descricao: "descrição",
  revisao: "revisão",
  operacao: "operação",
  situacao: "situação",
  convencao: "convenção",
  permissao: "permissão",
  permissoes: "permissões",
  sessao: "sessão",
  sessoes: "sessões",
  ficheiros: "ficheiros",
  ficheiro: "ficheiro",
  upload: "upload",
  download: "download",
  login: "login",
  logout: "logout",
  registo: "registo",
  relatorio: "relatório",
  relatorios: "relatórios",
  tutorial: "tutorial",
  exemplos: "exemplos",
  exemplo: "exemplo",
  modelo: "modelo",
  modelos: "modelos",
  fluxo: "fluxo",
  processo: "processo",
  processos: "processos",
  atividades: "atividades",
  atividade: "atividade",
  webhook: "webhook",
  webhooks: "webhooks",
  token: "token",
  tokens: "tokens",
  codigo: "código",
  codigos: "códigos",
  indices: "índices",
  formulario: "formulário",
  formularios: "formulários",
  historico: "histórico",
  historicos: "históricos",
  criterio: "critério",
  criterios: "critérios",
};

function slugTokenToWord(raw: string): string {
  const t = raw.toLowerCase();
  if (!t) return raw;
  if (/^\d+$/.test(t)) return raw;
  if (ACRONYMS[t]) return ACRONYMS[t];
  if (WORD_FIX[t]) return WORD_FIX[t];

  let w = t;

  if (w.endsWith("acoes") && w.length > 5) w = `${w.slice(0, -5)}ações`;
  else if (w.endsWith("acao") && w.length > 4) w = `${w.slice(0, -4)}ação`;
  else if (w.endsWith("ucao") && w.length > 4) w = `${w.slice(0, -4)}ução`;
  else if (w.endsWith("icao") && w.length > 4) w = `${w.slice(0, -4)}ição`;
  else if (w.endsWith("coes") && w.length > 4) w = `${w.slice(0, -4)}ções`;
  else if (w.endsWith("oes") && w.length > 3 && !w.endsWith("acoes") && !w.endsWith("icoes")) w = `${w.slice(0, -3)}ões`;
  else if (w.endsWith("aes") && w.length > 3) w = `${w.slice(0, -3)}ães`;
  else if (w.endsWith("cao") && w.length > 3 && !w.endsWith("acao") && !w.endsWith("icao") && !w.endsWith("ucao")) {
    w = `${w.slice(0, -3)}ção`;
  } else if (w.endsWith("ocio") && w.length > 4) w = `${w.slice(0, -4)}ócio`;
  else if (w.endsWith("icios") && w.length > 5) w = `${w.slice(0, -5)}ícios`;
  else if (w.endsWith("icio") && w.length > 4) w = `${w.slice(0, -4)}ício`;

  return w;
}

function capitalizeWord(word: string): string {
  if (!word) return word;
  if (/^\d+$/.test(word)) return word;
  if (/^[A-Z0-9]{2,}$/.test(word) && word.length <= 6) return word;
  const first = word.charAt(0);
  const rest = word.slice(1);
  return first.toLocaleUpperCase("pt-BR") + rest;
}

/**
 * Converte o nome do ficheiro (ex.: `02-documentacao-processo.md`) em título legível.
 */
export function wikiDocumentDisplayName(fileName: string): string {
  const base = fileName.replace(/\.(md|xml)$/i, "").trim();
  if (!base) return fileName;

  const segments = base.split("-").filter((s) => s.length > 0);
  const words = segments.map((seg) => capitalizeWord(slugTokenToWord(seg)));
  return words.join(" ");
}
