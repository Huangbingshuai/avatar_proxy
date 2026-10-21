import { CircleDollarSign, DatabaseBackup, HardDrive, ScrollText, Server, ShieldCheck, UserRoundCog } from "lucide-react";

export const adminSections = [
  { id: "admins", label: "安全管理", icon: ShieldCheck, title: "超级管理员控制中心", description: "管理TOTP验证器、登录告警与会话；其他管理功能请从左侧独立菜单进入。" },
  { id: "admin-users", label: "管理员账号", icon: UserRoundCog, title: "管理员账号管理", description: "创建普通管理员、重置密码与管理账号状态；项目及日常业务仍由普通管理员处理。" },
  { id: "admin-channels", label: "供应商渠道", icon: Server, title: "供应商渠道管理", description: "按客户项目维护上游凭证与连通状态，不改变现有项目绑定和业务Key。" },
  { id: "admin-rates", label: "全局模型价目", icon: CircleDollarSign, title: "全局模型价格管理", description: "统一维护模型价格和生效月份；项目账单及结算规则由普通管理员处理。" },
  { id: "admin-monitor", label: "磁盘与邮件", icon: HardDrive, title: "磁盘监控与邮件通知", description: "查看服务器磁盘用量，设置告警规则、发件账号和收件人；监控由后端独立运行。" },
  { id: "admin-backups", label: "备份与恢复", icon: DatabaseBackup, title: "数据备份与恢复", description: "查看自动备份、校验文件及恢复数据库；恢复操作会覆盖备份时间之后的数据。" },
  { id: "admin-audits", label: "安全审计", icon: ScrollText, title: "管理员安全审计记录", description: "追溯登录、账号变更和安全操作；来源IP仅用于审计，不作为访问限制。" },
] as const;

export type AdminSection = typeof adminSections[number]["id"];

export function isAdminSection(value: string): value is AdminSection {
  return adminSections.some((section) => section.id === value);
}
