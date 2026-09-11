"use client";

import {
  AudioLines,
  CloudCog,
  Image as ImageIcon,
  MessageSquareText,
  Network,
  Search,
  Video,
} from "lucide-react";
import type { ReactNode } from "react";

import { getProviderIconPath } from "./model-icon-library";

export type ModelFilterItem = {
  model: string;
  displayName: string;
  provider: string;
  modality: string;
};

type FilterOption = {
  value: string;
  label: string;
  count?: number;
};

type ModelCatalogFiltersProps = {
  items: ModelFilterItem[];
  provider: string;
  modality: string;
  search: string;
  onProviderChange: (value: string) => void;
  onModalityChange: (value: string) => void;
  onSearchChange: (value: string) => void;
  providerLabels: Record<string, string>;
  modalityLabels: Record<string, string>;
  resultCount: number;
  searchLabel: string;
  searchPlaceholder?: string;
  status?: {
    value: string;
    onChange: (value: string) => void;
    options: FilterOption[];
  };
  children?: ReactNode;
  className?: string;
};

function ProviderIcon({ provider }: { provider: string }) {
  const icon = getProviderIconPath(provider);
  if (!icon) return <CloudCog aria-hidden="true" size={16} />;
  // Provider marks are small local UI assets and do not benefit from responsive image loading.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={icon} width={16} height={16} alt="" aria-hidden="true" />;
}

function ModalityIcon({ modality }: { modality: string }) {
  if (modality === "image") return <ImageIcon size={14} />;
  if (modality === "video") return <Video size={14} />;
  if (modality === "embedding") return <Network size={14} />;
  if (modality === "audio") return <AudioLines size={14} />;
  return <MessageSquareText size={14} />;
}

function availableOptions(
  values: string[],
  labels: Record<string, string>,
): FilterOption[] {
  return Array.from(new Set(values))
    .map((value) => ({ value, label: labels[value] ?? value }))
    .sort((left, right) => left.label.localeCompare(right.label, "zh-CN"));
}

export default function ModelCatalogFilters({
  items,
  provider,
  modality,
  search,
  onProviderChange,
  onModalityChange,
  onSearchChange,
  providerLabels,
  modalityLabels,
  resultCount,
  searchLabel,
  searchPlaceholder = "搜索模型名称或别名...",
  status,
  children,
  className = "",
}: ModelCatalogFiltersProps) {
  const providerOptions = availableOptions(items.map((item) => item.provider), providerLabels);
  const modalityOptions = availableOptions(items.map((item) => item.modality), modalityLabels);

  return (
    <div className={`relayMarketFilters modelCatalogFilters ${className}`.trim()}>
      <div className="relayFilterLine">
        <span>厂商</span>
        <div>
          <button type="button" className={!provider ? "active" : ""} aria-pressed={!provider} onClick={() => onProviderChange("")}>全部</button>
          {providerOptions.map((option) => (
            <button type="button" className={provider === option.value ? "active" : ""} aria-pressed={provider === option.value} onClick={() => onProviderChange(option.value)} key={option.value}>
              <ProviderIcon provider={option.value} />
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <div className="relayFilterLine">
        <span>类型</span>
        <div>
          <button type="button" className={!modality ? "active" : ""} aria-pressed={!modality} onClick={() => onModalityChange("")}>全部</button>
          {modalityOptions.map((option) => (
            <button type="button" className={modality === option.value ? "active" : ""} aria-pressed={modality === option.value} onClick={() => onModalityChange(option.value)} key={option.value}>
              <ModalityIcon modality={option.value} />
              {option.label}
            </button>
          ))}
        </div>
      </div>
      {status && (
        <div className="relayFilterLine">
          <span>状态</span>
          <div>
            {status.options.map((option) => (
              <button type="button" className={status.value === option.value ? "active" : ""} aria-pressed={status.value === option.value} onClick={() => status.onChange(option.value)} key={option.value}>
                {option.label}
                {typeof option.count === "number" && <small>{option.count}</small>}
              </button>
            ))}
          </div>
        </div>
      )}
      {children}
      <div className="relayFilterLine search">
        <span>搜索</span>
        <label>
          <Search size={16} />
          <input aria-label={searchLabel} value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder={searchPlaceholder} />
        </label>
        <small>显示 {resultCount} / {items.length} 个模型</small>
      </div>
    </div>
  );
}
