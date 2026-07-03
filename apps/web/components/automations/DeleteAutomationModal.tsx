import { Modal } from "@/components/ui/Modal";
import type { AutomationOut } from "@/lib/types";

interface Props {
  automation: AutomationOut;
  onClose: () => void;
  onConfirm: () => void;
}

export function DeleteAutomationModal({ automation, onClose, onConfirm }: Props) {
  return (
    <Modal
      open
      onClose={onClose}
      title="Удалить автоматизацию?"
      dismissOnBackdrop={false}
    >
      <>
        <h3 className="text-base font-bold mb-2">Удалить автоматизацию?</h3>
        <p className="text-sm text-brand-muted mb-5">
          Автоматизация{" "}
          <span className="font-semibold text-brand-primary">«{automation.name}»</span>{" "}
          будет удалена. Запущенные шаги текущих исполнений сохранятся в истории.
        </p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-sm font-semibold text-brand-muted hover:text-brand-primary"
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-4 py-1.5 text-sm font-semibold bg-rose text-white rounded-full hover:bg-rose/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose focus-visible:ring-offset-2"
          >
            Удалить
          </button>
        </div>
      </>
    </Modal>
  );
}
