// 从 services/api.ts 迁出：图标类名是渲染细节，不是"与后端对话"的一部分。
const ICONS: Record<string, string> = {
  PDF: "fas fa-file-pdf",
  Word: "fas fa-file-word",
  Excel: "fas fa-file-excel",
}

export function fileIcon(fileType: string): string {
  return ICONS[fileType] || "fas fa-file"
}
