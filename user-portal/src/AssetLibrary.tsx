import {
  AudioLines,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Edit3,
  FolderPlus,
  Image as ImageIcon,
  Images,
  LoaderCircle,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  Video,
  X,
} from "lucide-react";
import {
  type ChangeEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  createAsset,
  createAssetGroup,
  deleteAsset,
  deleteAssetGroup,
  isAssetActive,
  listAssetGroups,
  listAssets,
  readCachedAssetGroups,
  readCachedAssets,
  updateAsset,
  updateAssetGroup,
  uploadAssetFile,
  type Asset,
  type AssetGroup,
  type AssetType,
  type PageResult,
} from "./api";

const EMPTY_GROUPS: PageResult<AssetGroup> = { items: [], total: 0, pageNumber: 1, pageSize: 20 };
const EMPTY_ASSETS: PageResult<Asset> = { items: [], total: 0, pageNumber: 1, pageSize: 20 };
const FAILED_ASSET_STATUSES = new Set(["failed", "error", "rejected", "inactive", "unavailable"]);
const MEBIBYTE = 1024 * 1024;
const FILE_ACCEPT = [
  ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".heic", ".heif",
  ".mp4", ".mov", ".wav", ".mp3",
].join(",");

type UploadRule = {
  assetType: AssetType;
  label: string;
  maxBytes: number;
  strictMaximum?: boolean;
};

const UPLOAD_RULES: Record<string, UploadRule> = Object.fromEntries([
  ...["jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff", "gif", "heic", "heif"]
    .map((extension) => [extension, { assetType: "Image", label: "图片", maxBytes: 30 * MEBIBYTE, strictMaximum: true }]),
  ...["mp4", "mov"]
    .map((extension) => [extension, { assetType: "Video", label: "视频", maxBytes: 200 * MEBIBYTE }]),
  ...["wav", "mp3"]
    .map((extension) => [extension, { assetType: "Audio", label: "音频", maxBytes: 15 * MEBIBYTE }]),
]);

type AssetLibraryProps = {
  apiKey: string;
  apiKeyValid: boolean;
  mode?: "manage" | "select";
  selectedAssets?: Asset[];
  maxSelection?: number;
  onSelectionChange?: (assets: Asset[]) => void;
  onMessage?: (message: string, tone: "notice" | "error") => void;
};

function assetStatusLabel(status: string) {
  const value = status.toLowerCase();
  if (value === "active") return "可用";
  if (value === "processing" || value === "pending" || value === "creating") return "处理中";
  if (FAILED_ASSET_STATUSES.has(value)) return "不可用";
  return status || "状态未知";
}

function assetTypeOf(asset: Asset): AssetType {
  return asset.assetType || "Image";
}

function assetTypeLabel(assetType: AssetType) {
  if (assetType === "Video") return "视频";
  if (assetType === "Audio") return "音频";
  return "图片";
}

function uploadRuleFor(file: File) {
  const extension = file.name.split(".").pop()?.toLowerCase() || "";
  return UPLOAD_RULES[extension];
}

function uploadProblem(file: File, rule?: UploadRule) {
  if (!file.size) return "不能上传空文件";
  if (!rule) return "不支持该文件格式，请选择方舟支持的图片、视频或音频";
  const tooLarge = rule.strictMaximum ? file.size >= rule.maxBytes : file.size > rule.maxBytes;
  if (tooLarge) return `${rule.label}文件大小不能超过 ${Math.round(rule.maxBytes / MEBIBYTE)}MB`;
  return "";
}

function formatFileSize(value: number) {
  if (value >= MEBIBYTE) return `${(value / MEBIBYTE).toFixed(value >= 10 * MEBIBYTE ? 0 : 1)}MB`;
  return `${Math.max(1, Math.round(value / 1024))}KB`;
}

function AssetThumbnail({ asset }: { asset: Asset }) {
  const [failed, setFailed] = useState(false);
  const assetType = assetTypeOf(asset);
  if (assetType === "Audio") {
    return <div className="assetImageFallback audio"><AudioLines size={30} /><span>音频素材</span></div>;
  }
  if (!asset.previewUrl || failed) {
    return <div className={`assetImageFallback ${assetType.toLowerCase()}`}>{assetType === "Video" ? <Video size={30} /> : <ImageIcon size={28} />}<span>{assetType === "Video" ? "视频预览" : "暂无预览"}</span></div>;
  }
  if (assetType === "Video") {
    return <video src={asset.previewUrl} aria-label={asset.name} preload="metadata" muted playsInline onError={() => setFailed(true)} />;
  }
  return <img src={asset.previewUrl} alt={asset.name} loading="lazy" onError={() => setFailed(true)} />;
}

function Pagination({ page, total, pageSize, onChange }: { page: number; total: number; pageSize: number; onChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="pagination" aria-label="分页">
      <button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="上一页"><ChevronLeft size={16} /></button>
      <span>{page} / {pages}</span>
      <button type="button" disabled={page >= pages} onClick={() => onChange(page + 1)} aria-label="下一页"><ChevronRight size={16} /></button>
    </div>
  );
}

export default function AssetLibrary({
  apiKey,
  apiKeyValid,
  mode = "manage",
  selectedAssets = [],
  maxSelection = 9,
  onSelectionChange,
  onMessage,
}: AssetLibraryProps) {
  const [groups, setGroups] = useState(EMPTY_GROUPS);
  const [assets, setAssets] = useState(EMPTY_ASSETS);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [groupPage, setGroupPage] = useState(1);
  const [assetPage, setAssetPage] = useState(1);
  const [groupSearchDraft, setGroupSearchDraft] = useState("");
  const [groupSearch, setGroupSearch] = useState("");
  const [assetSearchDraft, setAssetSearchDraft] = useState("");
  const [assetSearch, setAssetSearch] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupDescription, setNewGroupDescription] = useState("");
  const [editingGroup, setEditingGroup] = useState<AssetGroup | null>(null);
  const [editingAsset, setEditingAsset] = useState<Asset | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [assetsLoading, setAssetsLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [pollUntil, setPollUntil] = useState(0);
  const [pollTick, setPollTick] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectedAssetsRef = useRef(selectedAssets);
  const onSelectionChangeRef = useRef(onSelectionChange);
  const groupRequestRef = useRef(0);
  const assetRequestRef = useRef(0);

  useEffect(() => {
    selectedAssetsRef.current = selectedAssets;
    onSelectionChangeRef.current = onSelectionChange;
  }, [onSelectionChange, selectedAssets]);

  const message = useCallback((value: string, tone: "notice" | "error") => {
    onMessage?.(value, tone);
  }, [onMessage]);

  const loadGroups = useCallback(async (
    silent = false,
    cacheFirst = false,
    override?: { pageNumber?: number; name?: string },
  ) => {
    const requestId = groupRequestRef.current + 1;
    groupRequestRef.current = requestId;
    if (!apiKeyValid) {
      setGroups(EMPTY_GROUPS);
      return EMPTY_GROUPS;
    }
    const pageNumber = override?.pageNumber ?? groupPage;
    const name = override?.name ?? groupSearch;
    const options = { pageNumber, pageSize: 20, name };
    const cached = cacheFirst ? readCachedAssetGroups(apiKey, options) : null;
    if (cached) {
      setGroups(cached);
      setSelectedGroupId((current) => current || cached.items[0]?.id || "");
      setGroupsLoading(false);
    }
    if (!silent && !cached) setGroupsLoading(true);
    try {
      const result = await listAssetGroups(apiKey, options);
      if (groupRequestRef.current !== requestId) return result;
      setGroups(result);
      setSelectedGroupId((current) => {
        if (!current) return result.items[0]?.id || "";
        if (pageNumber === 1 && !name && !result.items.some((group) => group.id === current)) {
          return result.items[0]?.id || "";
        }
        return current;
      });
      return result;
    } catch (caught) {
      if (groupRequestRef.current === requestId) {
        message(caught instanceof Error ? caught.message : "素材库加载失败", "error");
      }
      return cached || EMPTY_GROUPS;
    } finally {
      if (groupRequestRef.current === requestId && !silent && !cached) setGroupsLoading(false);
    }
  }, [apiKey, apiKeyValid, groupPage, groupSearch, message]);

  const loadAssets = useCallback(async (silent = false, cacheFirst = false) => {
    const requestId = assetRequestRef.current + 1;
    assetRequestRef.current = requestId;
    if (!apiKeyValid || !selectedGroupId) {
      setAssets(EMPTY_ASSETS);
      return EMPTY_ASSETS;
    }
    const options = { pageNumber: assetPage, pageSize: 20, name: assetSearch };
    const cached = cacheFirst ? readCachedAssets(apiKey, selectedGroupId, options) : null;
    if (cached) {
      setAssets(cached);
      setAssetsLoading(false);
    }
    if (!silent && !cached) setAssetsLoading(true);
    try {
      const result = await listAssets(apiKey, selectedGroupId, options);
      if (assetRequestRef.current !== requestId) return result;
      setAssets(result);
      const visibleById = new Map(result.items.map((item) => [item.id, item]));
      const nextSelection = selectedAssetsRef.current.filter((selected) => {
        const visible = visibleById.get(selected.id);
        return !visible || (isAssetActive(visible) && assetTypeOf(visible) === "Image");
      });
      if (nextSelection.length !== selectedAssetsRef.current.length) {
        onSelectionChangeRef.current?.(nextSelection);
      }
      return result;
    } catch (caught) {
      if (assetRequestRef.current === requestId) {
        message(caught instanceof Error ? caught.message : "素材加载失败", "error");
      }
      return cached || EMPTY_ASSETS;
    } finally {
      if (assetRequestRef.current === requestId && !silent && !cached) setAssetsLoading(false);
    }
  }, [apiKey, apiKeyValid, assetPage, assetSearch, message, selectedGroupId]);

  useEffect(() => {
    let ignore = false;
    async function run() {
      await Promise.resolve();
      if (!ignore) await loadGroups(false, true);
    }
    void run();
    return () => { ignore = true; };
  }, [loadGroups]);

  useEffect(() => {
    let ignore = false;
    async function run() {
      await Promise.resolve();
      if (!ignore) await loadAssets(false, true);
    }
    void run();
    return () => { ignore = true; };
  }, [loadAssets]);

  useEffect(() => {
    if (!pollUntil || !selectedGroupId || Date.now() >= pollUntil) return undefined;
    let disposed = false;
    const timer = window.setTimeout(async () => {
      const result = await loadAssets(true);
      if (disposed) return;
      const hasProcessing = result.items.some((asset) => {
        const status = asset.status.toLowerCase();
        return !isAssetActive(asset) && !FAILED_ASSET_STATUSES.has(status);
      });
      if (!hasProcessing || Date.now() >= pollUntil) setPollUntil(0);
      else setPollTick((value) => value + 1);
    }, 3000);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [loadAssets, pollTick, pollUntil, selectedGroupId]);

  function selectGroup(groupId: string) {
    setSelectedGroupId(groupId);
    setAssetPage(1);
    setAssetSearch("");
    setAssetSearchDraft("");
  }

  async function handleCreateGroup(event: FormEvent) {
    event.preventDefault();
    const name = newGroupName.trim();
    const description = newGroupDescription.trim();
    if (!name) return;
    setBusy("create-group");
    try {
      const createdGroupId = await createAssetGroup(apiKey, name, description);
      setNewGroupName("");
      setNewGroupDescription("");
      setGroupPage(1);
      setGroupSearch("");
      setGroupSearchDraft("");
      const refreshed = await loadGroups(false, false, { pageNumber: 1, name: "" });
      const nextGroupId = createdGroupId || refreshed.items.find((group) => group.name === name)?.id;
      if (nextGroupId) selectGroup(nextGroupId);
      message("素材库已创建", "notice");
    } catch (caught) {
      message(caught instanceof Error ? caught.message : "创建素材库失败", "error");
    } finally {
      setBusy("");
    }
  }

  async function handleUpdateGroup(event: FormEvent) {
    event.preventDefault();
    if (!editingGroup?.name.trim()) return;
    setBusy(`group-${editingGroup.id}`);
    try {
      await updateAssetGroup(apiKey, editingGroup.id, editingGroup.name, editingGroup.description);
      setEditingGroup(null);
      await loadGroups(true);
      message("素材库信息已更新", "notice");
    } catch (caught) {
      message(caught instanceof Error ? caught.message : "更新素材库失败", "error");
    } finally {
      setBusy("");
    }
  }

  async function handleDeleteGroup(group: AssetGroup) {
    setBusy(`group-${group.id}`);
    try {
      const contents = await listAssets(apiKey, group.id, { pageNumber: 1, pageSize: 1 });
      if (contents.total > 0 || contents.items.length > 0) {
        message("该素材库中仍有素材，请先删除全部素材后再删除素材库", "error");
        return;
      }
      if (!window.confirm(`确认删除素材库“${group.name}”？此操作不可撤销。`)) return;
      await deleteAssetGroup(apiKey, group.id);
      if (selectedGroupId === group.id) setSelectedGroupId("");
      setGroups((current) => ({ ...current, items: current.items.filter((item) => item.id !== group.id), total: Math.max(0, current.total - 1) }));
      message("素材库已删除", "notice");
      await loadGroups(true);
    } catch (caught) {
      message(caught instanceof Error ? caught.message : "删除素材库失败", "error");
    } finally {
      setBusy("");
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] || null;
    const rule = file ? uploadRuleFor(file) : undefined;
    const problem = file ? uploadProblem(file, rule) : "";
    if (problem) {
      message(problem, "error");
      event.target.value = "";
      setUploadFile(null);
      return;
    }
    setUploadFile(file);
    if (file && !uploadName) setUploadName(file.name.replace(/\.[^.]+$/, "").slice(0, 64));
  }

  async function handleUpload(event: FormEvent) {
    event.preventDefault();
    if (!selectedGroupId || !uploadFile) return;
    const rule = uploadRuleFor(uploadFile);
    const problem = uploadProblem(uploadFile, rule);
    if (problem || !rule) {
      message(problem || "无法识别素材类型", "error");
      return;
    }
    setBusy("upload");
    try {
      const uploaded = await uploadAssetFile(uploadFile, apiKey);
      if (!uploaded.url) throw new Error("文件已上传，但没有取得可用于入库的地址");
      if ((uploaded.assetType || rule.assetType) !== rule.assetType) throw new Error("服务端识别的素材类型与所选文件不一致");
      await createAsset(apiKey, selectedGroupId, uploaded, uploadName);
      setUploadFile(null);
      setUploadName("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      setAssetPage(1);
      setPollUntil(Date.now() + 120_000);
      setPollTick((value) => value + 1);
      await loadAssets();
      message(`${assetTypeLabel(uploaded.assetType || rule.assetType)}已提交入库，请等待方舟处理完成`, "notice");
    } catch (caught) {
      message(caught instanceof Error ? caught.message : "素材入库失败，请重试", "error");
    } finally {
      setBusy("");
    }
  }

  async function handleUpdateAsset(event: FormEvent) {
    event.preventDefault();
    if (!editingAsset?.name.trim()) return;
    setBusy(`asset-${editingAsset.id}`);
    try {
      await updateAsset(apiKey, editingAsset.id, editingAsset.name);
      setEditingAsset(null);
      await loadAssets(true);
      if (selectedAssets.some((asset) => asset.id === editingAsset.id)) {
        onSelectionChange?.(selectedAssets.map((asset) => asset.id === editingAsset.id ? { ...asset, name: editingAsset.name.trim() } : asset));
      }
      message("素材名称已更新", "notice");
    } catch (caught) {
      message(caught instanceof Error ? caught.message : "更新素材失败", "error");
    } finally {
      setBusy("");
    }
  }

  async function handleDeleteAsset(asset: Asset) {
    if (!window.confirm(`确认删除素材“${asset.name}”？此操作不可撤销。`)) return;
    setBusy(`asset-${asset.id}`);
    try {
      await deleteAsset(apiKey, asset.id);
      setAssets((current) => ({ ...current, items: current.items.filter((item) => item.id !== asset.id), total: Math.max(0, current.total - 1) }));
      if (selectedAssets.some((selected) => selected.id === asset.id)) {
        onSelectionChange?.(selectedAssets.filter((selected) => selected.id !== asset.id));
      }
      message("素材已删除", "notice");
    } catch (caught) {
      message(caught instanceof Error ? caught.message : "删除素材失败", "error");
    } finally {
      setBusy("");
    }
  }

  if (!apiKeyValid) {
    return (
      <div className="libraryLocked">
        <CircleAlert size={24} />
        <div><b>先连接你的项目</b><p>输入有效的业务 API Key 后，才能读取该项目中的素材库。</p></div>
      </div>
    );
  }

  const selectedGroup = groups.items.find((group) => group.id === selectedGroupId);
  const selectedUploadRule = uploadFile ? uploadRuleFor(uploadFile) : undefined;

  function toggleAsset(asset: Asset) {
    if (assetTypeOf(asset) !== "Image") {
      message("视频生成仅支持选择图片；视频和音频可在素材库中管理", "error");
      return;
    }
    const selected = selectedAssets.some((item) => item.id === asset.id);
    if (selected) {
      onSelectionChange?.(selectedAssets.filter((item) => item.id !== asset.id));
      return;
    }
    if (selectedAssets.length >= maxSelection) {
      message(`最多选择 ${maxSelection} 张参考图片`, "error");
      return;
    }
    onSelectionChange?.([...selectedAssets, asset]);
  }

  return (
    <div className={`assetLibrary ${mode === "select" ? "isPicker" : ""}`}>
      <aside className="groupShelf" aria-label="素材库列表">
        <div className="librarySectionHeading">
          <div><span>ASSET REELS</span><h3>素材库</h3></div>
          <button type="button" className="squareButton" onClick={() => void loadGroups()} disabled={groupsLoading} aria-label="刷新素材库"><RefreshCw size={16} className={groupsLoading ? "spin" : ""} /></button>
        </div>
        {mode === "manage" ? (
          <form className="createGroupForm" onSubmit={handleCreateGroup}>
            <label className="inputWithIcon">
              <span className="visuallyHidden">新素材库名称</span>
              <FolderPlus size={16} aria-hidden="true" />
              <input value={newGroupName} maxLength={128} autoComplete="off" onChange={(event) => setNewGroupName(event.target.value)} placeholder="新素材库名称" />
            </label>
            <input className="plainInput" aria-label="素材库用途说明" value={newGroupDescription} maxLength={1000} onChange={(event) => setNewGroupDescription(event.target.value)} placeholder="用途说明（可选）" />
            <button type="submit" className="secondaryButton" disabled={!newGroupName.trim() || busy === "create-group"}>{busy === "create-group" ? <LoaderCircle size={15} className="spin" /> : <FolderPlus size={15} />}创建素材库</button>
          </form>
        ) : null}
        <form className="compactSearch" onSubmit={(event) => { event.preventDefault(); setGroupPage(1); setGroupSearch(groupSearchDraft); }}>
          <Search size={14} /><input value={groupSearchDraft} onChange={(event) => setGroupSearchDraft(event.target.value)} placeholder="搜索素材库" /><button type="submit">查找</button>
        </form>
        <div className="groupList">
          {groupsLoading ? <div className="smallLoading"><LoaderCircle className="spin" size={18} />加载素材库</div> : null}
          {!groupsLoading && !groups.items.length ? <div className="compactEmpty"><Images size={22} /><span>{groupSearch ? "没有匹配的素材库" : "创建第一个素材库"}</span></div> : null}
          {groups.items.map((group) => (
            <div key={group.id} className={`groupItem ${selectedGroupId === group.id ? "selected" : ""}`}>
              {editingGroup?.id === group.id ? (
                <form className="inlineEdit" onSubmit={handleUpdateGroup}>
                  <input value={editingGroup.name} onChange={(event) => setEditingGroup({ ...editingGroup, name: event.target.value })} aria-label="素材库名称" autoFocus />
                  <input value={editingGroup.description} onChange={(event) => setEditingGroup({ ...editingGroup, description: event.target.value })} aria-label="素材库说明" placeholder="用途说明" />
                  <span><button type="submit" aria-label="保存"><Check size={14} /></button><button type="button" onClick={() => setEditingGroup(null)} aria-label="取消"><X size={14} /></button></span>
                </form>
              ) : (
                <>
                  <button type="button" className="groupSelect" onClick={() => selectGroup(group.id)}>
                    <span className="reelIcon"><span /><span /><span /></span>
                    <span><b>{group.name}</b><small>{group.description || (group.assetCount === undefined ? "项目素材库" : `${group.assetCount} 项素材`)}</small></span>
                  </button>
                  {mode === "manage" ? <div className="itemTools"><button type="button" onClick={() => setEditingGroup({ ...group })} aria-label={`重命名 ${group.name}`}><Edit3 size={13} /></button><button type="button" onClick={() => void handleDeleteGroup(group)} disabled={busy === `group-${group.id}`} aria-label={`删除 ${group.name}`}><Trash2 size={13} /></button></div> : null}
                </>
              )}
            </div>
          ))}
        </div>
        <Pagination page={groupPage} total={groups.total} pageSize={groups.pageSize} onChange={setGroupPage} />
      </aside>

      <section className="contactSheet" aria-label="项目素材">
        <div className="contactSheetTop">
          <div><span>MEDIA ASSETS</span><h3>{selectedGroup?.name || "选择一个素材库"}</h3><p>{mode === "select" ? `选择可用图片加入创作，最多 ${maxSelection} 张。` : "统一上传、整理并检查图片、视频和音频。"}</p></div>
          <button type="button" className="squareButton" onClick={() => void loadAssets()} disabled={!selectedGroupId || assetsLoading} aria-label="刷新素材"><RefreshCw size={16} className={assetsLoading ? "spin" : ""} /></button>
        </div>

        {mode === "manage" && selectedGroupId ? (
          <form className="assetUploadBar" onSubmit={handleUpload}>
            <input ref={fileInputRef} className="visuallyHidden" type="file" accept={FILE_ACCEPT} onChange={handleFileChange} />
            <button type="button" className="chooseFileButton" onClick={() => fileInputRef.current?.click()}><Upload size={16} /><span>{uploadFile?.name || "选择图片、视频或音频"}</span></button>
            <input className="plainInput" value={uploadName} maxLength={64} onChange={(event) => setUploadName(event.target.value.slice(0, 64))} placeholder="素材名称（可选，最多64字符）" />
            <button type="submit" className="primaryButton" disabled={!uploadFile || busy === "upload"}>{busy === "upload" ? <LoaderCircle size={16} className="spin" /> : <Upload size={16} />}上传并入库</button>
            <div className="assetFormatGuide" aria-label="支持的素材格式">
              <span className="image"><ImageIcon size={15} /><b>图片</b><small>JPG / PNG / WebP / BMP / TIFF / GIF / HEIC / HEIF，&lt;30MB</small></span>
              <span className="video"><Video size={15} /><b>视频</b><small>MP4 / MOV，2–30秒，24–60FPS，≤200MB</small></span>
              <span className="audio"><AudioLines size={15} /><b>音频</b><small>WAV / MP3，2–30秒，≤15MB</small></span>
            </div>
            {uploadFile && selectedUploadRule ? <div className={`selectedUploadMeta ${selectedUploadRule.assetType.toLowerCase()}`}><b>{selectedUploadRule.label}</b><span>{formatFileSize(uploadFile.size)}</span><span>将按 {selectedUploadRule.assetType} 类型登记</span></div> : null}
            {busy === "upload" ? <div className="assetUploadProgress"><LoaderCircle size={14} className="spin" /><span>正在上传并登记素材，大文件处理期间请勿关闭页面</span></div> : null}
          </form>
        ) : null}

        {selectedGroupId ? (
          <div className="assetToolbar">
            <form className="compactSearch" onSubmit={(event) => { event.preventDefault(); setAssetPage(1); setAssetSearch(assetSearchDraft); }}>
              <Search size={14} /><input value={assetSearchDraft} onChange={(event) => setAssetSearchDraft(event.target.value)} placeholder="按名称查找素材" /><button type="submit">查找</button>
            </form>
            <span>{assets.total} 项素材{pollUntil ? " · 正在刷新处理状态" : ""}</span>
          </div>
        ) : null}

        {!selectedGroupId ? <div className="libraryEmpty"><Images size={34} /><b>从左侧选择素材库</b><p>图片、视频和音频都会按照素材库统一归档。</p></div> : null}
        {selectedGroupId && assetsLoading ? <div className="libraryEmpty"><LoaderCircle size={30} className="spin" /><b>正在装载素材</b></div> : null}
        {selectedGroupId && !assetsLoading && !assets.items.length ? <div className="libraryEmpty"><ImageIcon size={34} /><b>{assetSearch ? "没有匹配的素材" : "这个素材库还是空的"}</b><p>{mode === "manage" ? "上传第一项图片、视频或音频素材。" : "前往素材库工作区上传图片。"}</p></div> : null}

        {selectedGroupId && !assetsLoading && assets.items.length ? (
          <div className="assetGrid">
            {assets.items.map((asset) => {
              const active = isAssetActive(asset);
              const assetType = assetTypeOf(asset);
              const selectable = active && assetType === "Image";
              const selectedIndex = selectedAssets.findIndex((selected) => selected.id === asset.id);
              const selected = selectedIndex >= 0;
              return (
                <article key={asset.id} className={`assetCard ${selected ? "selected" : ""} ${active && (mode !== "select" || selectable) ? "" : "disabled"}`}>
                  <button type="button" className="assetPreview" disabled={!selectable || mode !== "select"} onClick={() => toggleAsset(asset)} aria-label={selectable ? `${selected ? "取消选择" : "选择"}${asset.name}` : `${asset.name} ${active ? "不可作为图片选择" : "暂不可用"}`}>
                    <AssetThumbnail asset={asset} />
                    <span className={`assetTypeBadge ${assetType.toLowerCase()}`}>{assetType === "Video" ? <Video size={11} /> : assetType === "Audio" ? <AudioLines size={11} /> : <ImageIcon size={11} />}{assetTypeLabel(assetType)}</span>
                    {mode === "select" && selectable ? <span className="selectionMark">{selected ? <><Check size={13} />图片{selectedIndex + 1}</> : "选择"}</span> : null}
                    <span className={`assetState ${active ? "active" : "pending"}`}>{active ? <CircleCheck size={12} /> : <LoaderCircle size={12} className={FAILED_ASSET_STATUSES.has(asset.status.toLowerCase()) ? "" : "spin"} />}{assetStatusLabel(asset.status)}</span>
                  </button>
                  {editingAsset?.id === asset.id ? (
                    <form className="assetInlineEdit" onSubmit={handleUpdateAsset}><input value={editingAsset.name} maxLength={64} onChange={(event) => setEditingAsset({ ...editingAsset, name: event.target.value.slice(0, 64) })} autoFocus aria-label="素材名称" /><button type="submit" aria-label="保存"><Check size={14} /></button><button type="button" onClick={() => setEditingAsset(null)} aria-label="取消"><X size={14} /></button></form>
                  ) : (
                    <div className="assetCaption"><span><b title={asset.name}>{asset.name}</b><small>{assetTypeLabel(assetType)} · {asset.createdAt || assetStatusLabel(asset.status)}</small></span>{mode === "manage" ? <span className="itemTools"><button type="button" onClick={() => setEditingAsset({ ...asset })} aria-label={`重命名 ${asset.name}`}><Edit3 size={13} /></button><button type="button" disabled={busy === `asset-${asset.id}`} onClick={() => void handleDeleteAsset(asset)} aria-label={`删除 ${asset.name}`}><Trash2 size={13} /></button></span> : null}</div>
                  )}
                </article>
              );
            })}
          </div>
        ) : null}
        <Pagination page={assetPage} total={assets.total} pageSize={assets.pageSize} onChange={setAssetPage} />
      </section>
    </div>
  );
}
