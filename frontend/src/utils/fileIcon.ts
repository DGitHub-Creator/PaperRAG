// 文件类型 → 展示色调（图标资源在 components/Icon.vue，这里只管类型语义）。
// As-Is：后端 file_type 实测是 PDF / Word / Excel 三种字面量，未知类型退回 other。
const TONES: Record<string, string> = {
  PDF: "pdf",
  Word: "word",
  Excel: "excel",
}

export function fileTone(fileType: string): string {
  return TONES[fileType] || "other"
}
