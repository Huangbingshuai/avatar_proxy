import { LexicalComposer } from "@lexical/react/LexicalComposer";
import { ContentEditable } from "@lexical/react/LexicalContentEditable";
import { LexicalErrorBoundary } from "@lexical/react/LexicalErrorBoundary";
import { HistoryPlugin } from "@lexical/react/LexicalHistoryPlugin";
import { useLexicalComposerContext } from "@lexical/react/LexicalComposerContext";
import { OnChangePlugin } from "@lexical/react/LexicalOnChangePlugin";
import { RichTextPlugin } from "@lexical/react/LexicalRichTextPlugin";
import {
  LexicalTypeaheadMenuPlugin,
  MenuOption,
  useBasicTypeaheadTriggerMatch,
} from "@lexical/react/LexicalTypeaheadMenuPlugin";
import {
  $createTextNode,
  $createParagraphNode,
  $getRoot,
  $getSelection,
  $isRangeSelection,
  $isElementNode,
  $nodesOfType,
  DecoratorNode,
  type LexicalEditor,
  type LexicalNode,
  type NodeKey,
  type SerializedLexicalNode,
  type Spread,
} from "lexical";
import {
  forwardRef,
  type ReactNode,
  type Ref,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { AudioLines, Image as ImageIcon, Video } from "lucide-react";
import { assetReferenceLabel, assetTypeOf, type Asset } from "./api";

type SerializedAssetMentionNode = Spread<{
  assetKey: string;
  label: string;
  type: "asset-mention";
  version: 1;
}, SerializedLexicalNode>;

class AssetMentionNode extends DecoratorNode<ReactNode> {
  __assetKey: string;
  __label: string;

  static getType() {
    return "asset-mention";
  }

  static clone(node: AssetMentionNode) {
    return new AssetMentionNode(node.__assetKey, node.__label, node.__key);
  }

  static importJSON(serializedNode: SerializedAssetMentionNode) {
    return $createAssetMentionNode(serializedNode.assetKey, serializedNode.label);
  }

  constructor(assetKey: string, label: string, key?: NodeKey) {
    super(key);
    this.__assetKey = assetKey;
    this.__label = label;
  }

  exportJSON(): SerializedAssetMentionNode {
    return {
      ...super.exportJSON(),
      assetKey: this.__assetKey,
      label: this.__label,
      type: "asset-mention",
      version: 1,
    };
  }

  createDOM() {
    const element = document.createElement("span");
    element.className = "assetMentionHost";
    return element;
  }

  updateDOM() {
    return false;
  }

  isInline() {
    return true;
  }

  getTextContent() {
    return this.__label;
  }

  getAssetKey() {
    return this.getLatest().__assetKey;
  }

  getLabel() {
    return this.getLatest().__label;
  }

  setLabel(label: string) {
    const writable = this.getWritable();
    writable.__label = label;
  }

  decorate() {
    return <span className="assetMentionChip" contentEditable={false}>@{this.__label}</span>;
  }
}

function $createAssetMentionNode(assetKey: string, label: string) {
  return new AssetMentionNode(assetKey, label);
}

class AssetMentionOption extends MenuOption {
  asset: Asset;
  label: string;

  constructor(asset: Asset, label: string) {
    super(asset.id);
    this.asset = asset;
    this.label = label;
  }
}

export type AssetPromptValue = {
  text: string;
  mentionedAssetIds: string[];
  serialized: string;
};

export type AssetPromptEditorHandle = {
  focus: () => void;
  insertAsset: (assetId: string) => void;
};

type AssetPromptEditorProps = {
  selectedAssets: Asset[];
  initialState?: string;
  initialText?: string;
  placeholder: string;
  onChange: (value: AssetPromptValue) => void;
};

function insertMention(editor: LexicalEditor, asset: Asset, label: string, nodeToReplace?: LexicalNode | null) {
  editor.update(() => {
    const mentionNode = $createAssetMentionNode(asset.id, label);
    if (nodeToReplace) nodeToReplace.replace(mentionNode);
    else {
      const selection = $getSelection();
      if ($isRangeSelection(selection)) selection.insertNodes([mentionNode]);
      else {
        const root = $getRoot();
        const lastChild = root.getLastChild();
        if ($isElementNode(lastChild)) lastChild.append(mentionNode);
        else root.append($createParagraphNode().append(mentionNode));
      }
    }
    const spaceNode = $createTextNode(" ");
    mentionNode.insertAfter(spaceNode);
    spaceNode.selectEnd();
  });
}

function AssetMentionPlugins({
  selectedAssets,
  onChange,
  editorRef,
}: {
  selectedAssets: Asset[];
  onChange: (value: AssetPromptValue) => void;
  editorRef: Ref<AssetPromptEditorHandle>;
}) {
  const [editor] = useLexicalComposerContext();
  const [query, setQuery] = useState<string | null>(null);
  const assetMap = useMemo(() => new Map(selectedAssets.map((asset) => [asset.id, { asset, label: assetReferenceLabel(asset, selectedAssets) }])), [selectedAssets]);
  const triggerMatch = useBasicTypeaheadTriggerMatch("@", { minLength: 0, maxLength: 32 });
  const options = useMemo(() => {
    const keyword = query?.toLowerCase().trim() || "";
    return selectedAssets.flatMap((asset) => {
      const label = assetReferenceLabel(asset, selectedAssets);
      return !keyword || label.includes(keyword) || asset.name.toLowerCase().includes(keyword)
        ? [new AssetMentionOption(asset, label)]
        : [];
    });
  }, [query, selectedAssets]);

  useImperativeHandle(editorRef, () => ({
    focus: () => editor.focus(),
    insertAsset: (assetId: string) => {
      const entry = assetMap.get(assetId);
      if (entry) insertMention(editor, entry.asset, entry.label);
    },
  }), [assetMap, editor]);

  useEffect(() => {
    editor.update(() => {
      for (const node of $nodesOfType(AssetMentionNode)) {
        const entry = assetMap.get(node.getAssetKey());
        if (!entry) node.remove();
        else if (node.getLabel() !== entry.label) node.setLabel(entry.label);
      }
    });
  }, [assetMap, editor]);

  return (
    <>
      <OnChangePlugin onChange={(editorState) => {
        editorState.read(() => {
          const mentionedAssetIds = Array.from(new Set($nodesOfType(AssetMentionNode).map((node) => node.getAssetKey())));
          onChange({
            text: $getRoot().getTextContent(),
            mentionedAssetIds,
            serialized: JSON.stringify(editorState.toJSON()),
          });
        });
      }} />
      <LexicalTypeaheadMenuPlugin<AssetMentionOption>
        triggerFn={triggerMatch}
        onQueryChange={setQuery}
        options={options}
        onSelectOption={(option, nodeToReplace, closeMenu) => {
          insertMention(editor, option.asset, option.label, nodeToReplace);
          closeMenu();
        }}
        menuRenderFn={(anchorRef, menuProps) => anchorRef.current && options.length
          ? createPortal(
            <div className="assetMentionMenu" role="listbox" aria-label="选择参考素材">
              <div className="mentionMenuTitle">引用已选素材</div>
              {menuProps.options.map((option, index) => (
                <button
                  key={option.key}
                  type="button"
                  ref={option.setRefElement}
                  role="option"
                  aria-selected={menuProps.selectedIndex === index}
                  className={menuProps.selectedIndex === index ? "active" : ""}
                  onMouseEnter={() => menuProps.setHighlightedIndex(index)}
                  onClick={() => menuProps.selectOptionAndCleanUp(option)}
                >
                  <span className={`mentionMenuThumb ${assetTypeOf(option.asset).toLowerCase()}`}>
                    {assetTypeOf(option.asset) === "Image" && option.asset.previewUrl ? <img src={option.asset.previewUrl} alt="" /> : null}
                    {assetTypeOf(option.asset) === "Image" && !option.asset.previewUrl ? <ImageIcon size={16} /> : null}
                    {assetTypeOf(option.asset) === "Video" ? <Video size={16} /> : null}
                    {assetTypeOf(option.asset) === "Audio" ? <AudioLines size={16} /> : null}
                  </span>
                  <span><b>{option.label}</b><small>{option.asset.name}</small></span>
                </button>
              ))}
            </div>,
            anchorRef.current,
          )
          : null}
      />
    </>
  );
}

function AssetPromptEditorComponent(
  { selectedAssets, initialState, initialText, placeholder, onChange }: AssetPromptEditorProps,
  ref: Ref<AssetPromptEditorHandle>,
) {
  const [initialConfig] = useState(() => ({
    namespace: "SeedanceAssetPrompt",
    nodes: [AssetMentionNode],
    editorState: initialState || (initialText
      ? () => {
        const paragraph = $createParagraphNode();
        paragraph.append($createTextNode(initialText));
        $getRoot().append(paragraph);
      }
      : undefined),
    theme: {
      paragraph: "promptParagraph",
    },
    onError: (error: Error) => { throw error; },
  }));

  return (
    <LexicalComposer initialConfig={initialConfig}>
      <div className="assetPromptEditor">
        <RichTextPlugin
          contentEditable={<ContentEditable className="assetPromptContent" aria-placeholder={placeholder} placeholder={<div className="assetPromptPlaceholder">{placeholder}</div>} />}
          ErrorBoundary={LexicalErrorBoundary}
        />
        <HistoryPlugin />
        <AssetMentionPlugins selectedAssets={selectedAssets} onChange={onChange} editorRef={ref} />
      </div>
    </LexicalComposer>
  );
}

const AssetPromptEditor = forwardRef(AssetPromptEditorComponent);
export default AssetPromptEditor;
