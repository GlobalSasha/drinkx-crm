"use client";

// Quote catalog management (Phase 1). Admin/head edit the DrinkX product
// catalog that Phase 2's quote builder picks line items from. Read is open;
// writes are gated server-side (admin/head) and hidden here for other roles.

import { useState } from "react";
import { Loader2, Plus, Trash2, Sparkles } from "lucide-react";

import {
  useProducts,
  useCreateProduct,
  useUpdateProduct,
  useDeactivateProduct,
  useSeedStarterCatalog,
} from "@/lib/hooks/use-products";
import { useMe } from "@/lib/hooks/use-me";
import { PRODUCT_CATEGORIES, type ProductOut } from "@/lib/types";
import { C } from "@/lib/design-system";

const CATEGORY_LABEL: Record<string, string> = {
  station: "Станция",
  service: "Сервис",
  install: "Монтаж",
  option: "Опция",
  other: "Другое",
};

export function CatalogSection() {
  const { data: products = [], isLoading } = useProducts();
  const me = useMe().data;
  const canEdit = me?.role === "admin" || me?.role === "head";

  const create = useCreateProduct();
  const seed = useSeedStarterCatalog();

  const [newName, setNewName] = useState("");
  const [newCategory, setNewCategory] = useState("station");
  const [newPrice, setNewPrice] = useState("");

  function addProduct() {
    const name = newName.trim();
    if (!name) return;
    create.mutate(
      { name, category: newCategory, unit_price: Number(newPrice) || 0 },
      {
        onSuccess: () => {
          setNewName("");
          setNewPrice("");
        },
      },
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-bold text-brand-primary">Каталог КП</h2>
        <p className="type-caption text-brand-muted mt-1">
          Позиции (станции, сервис, монтаж, опции) с ценами — из них собирается
          КП в карточке лида.
        </p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 size={18} className="animate-spin text-brand-muted" />
        </div>
      ) : products.length === 0 ? (
        <div className="rounded-card border border-brand-border bg-white p-6 text-center">
          <p className="type-caption text-brand-muted mb-3">
            Каталог пуст. Засеять стартовый набор DrinkX (цены потом поправишь)?
          </p>
          {canEdit && (
            <button
              type="button"
              onClick={() => seed.mutate()}
              disabled={seed.isPending}
              className="inline-flex items-center gap-1.5 px-4 py-2 type-caption font-semibold bg-brand-accent text-white rounded-full disabled:opacity-50"
            >
              {seed.isPending ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Sparkles size={13} />
              )}
              Засеять стартовый каталог
            </button>
          )}
        </div>
      ) : (
        <ul className="space-y-2">
          {products.map((p) => (
            <ProductRow key={p.id} product={p} canEdit={canEdit} />
          ))}
        </ul>
      )}

      {canEdit && products.length > 0 && (
        <div className="flex flex-wrap items-end gap-2 rounded-card border border-brand-border bg-white p-3">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Название позиции"
            className="flex-1 min-w-[10rem] type-body bg-brand-bg border border-brand-border rounded-lg px-2 py-1.5 outline-none focus:border-brand-accent"
          />
          <select
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            className="type-body bg-brand-bg border border-brand-border rounded-lg px-2 py-1.5 outline-none focus:border-brand-accent"
          >
            {PRODUCT_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABEL[c]}
              </option>
            ))}
          </select>
          <input
            value={newPrice}
            onChange={(e) => setNewPrice(e.target.value)}
            placeholder="Цена ₽"
            inputMode="numeric"
            className="w-28 type-body bg-brand-bg border border-brand-border rounded-lg px-2 py-1.5 outline-none focus:border-brand-accent"
          />
          <button
            type="button"
            onClick={addProduct}
            disabled={create.isPending || !newName.trim()}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 type-caption font-semibold ${C.button.ghost} disabled:opacity-50`}
          >
            <Plus size={13} />
            Добавить
          </button>
        </div>
      )}
    </div>
  );
}

function ProductRow({
  product,
  canEdit,
}: {
  product: ProductOut;
  canEdit: boolean;
}) {
  const update = useUpdateProduct();
  const deactivate = useDeactivateProduct();
  const [name, setName] = useState(product.name);
  const [price, setPrice] = useState(String(product.unit_price ?? 0));

  function saveName() {
    const v = name.trim();
    if (v && v !== product.name) update.mutate({ id: product.id, name: v });
  }
  function savePrice() {
    const n = Number(price) || 0;
    if (n !== Number(product.unit_price)) update.mutate({ id: product.id, unit_price: n });
  }

  return (
    <li className="flex flex-wrap items-center gap-2 rounded-card border border-brand-border bg-white px-3 py-2">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={saveName}
        disabled={!canEdit}
        className="flex-1 min-w-[10rem] type-body bg-transparent border border-transparent hover:border-brand-border rounded-lg px-2 py-1 outline-none focus:border-brand-accent disabled:opacity-70"
      />
      {canEdit ? (
        <select
          value={product.category}
          onChange={(e) => update.mutate({ id: product.id, category: e.target.value })}
          className="type-caption bg-brand-bg border border-brand-border rounded-lg px-2 py-1 outline-none focus:border-brand-accent"
        >
          {PRODUCT_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {CATEGORY_LABEL[c]}
            </option>
          ))}
        </select>
      ) : (
        <span className="type-caption text-brand-muted">{CATEGORY_LABEL[product.category] ?? product.category}</span>
      )}
      <input
        value={price}
        onChange={(e) => setPrice(e.target.value)}
        onBlur={savePrice}
        disabled={!canEdit}
        inputMode="numeric"
        className="w-28 type-body bg-transparent border border-transparent hover:border-brand-border rounded-lg px-2 py-1 outline-none focus:border-brand-accent disabled:opacity-70"
      />
      <span className="type-caption text-brand-muted">₽</span>
      {canEdit && (
        <button
          type="button"
          onClick={() => deactivate.mutate(product.id)}
          disabled={deactivate.isPending}
          aria-label="Убрать из каталога"
          className="ml-auto p-1.5 text-brand-muted hover:text-rose transition-colors disabled:opacity-50"
        >
          <Trash2 size={14} />
        </button>
      )}
    </li>
  );
}
