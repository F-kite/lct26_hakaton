const SOURCE_TYPE_LABELS: Record<string, string> = {
  academic_aggregator: "Научная база",
  preprint: "Препринт",
  doi_registry: "Научная публикация (DOI)",
  grant_database: "Грант",
  code_repository: "Репозиторий кода",
  community_forum: "Сообщество разработчиков",
  company_developer: "Сайт компании-разработчика",
  university: "Университет",
  international_organization: "Международная организация",
  industry_association: "Отраслевая ассоциация",
  industry_report: "Аналитический отчёт",
  professional_media: "Отраслевое медиа",
  science_media: "Научное медиа",
  tech_media: "Технологическое медиа",
  blog_platform: "Блог-платформа",
  analytical_report: "Аналитический отчёт",
};

export function sourceTypeLabel(type: string): string {
  return SOURCE_TYPE_LABELS[type] ?? type;
}

const RELATION_LABELS: Record<string, string> = {
  primary: "Основной источник",
  similar: "Близкая работа",
  cites: "Цитирует основную работу",
  related: "Связанная работа (OpenAlex)",
  assessment: "Оценка технологии",
  assessment_topic: "Оценка по теме запроса",
};

export function relationLabel(relation: string | null | undefined, isPrimary: boolean): string | null {
  if (relation) return RELATION_LABELS[relation] ?? null;
  return isPrimary ? RELATION_LABELS.primary : null;
}

export function isAssessment(relation: string | null | undefined): boolean {
  return Boolean(relation && relation.startsWith("assessment"));
}
