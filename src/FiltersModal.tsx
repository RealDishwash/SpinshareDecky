import { useState } from 'react';
import { ConfirmModal, DialogButton, DropdownItem, SliderField } from '@decky/ui';
import { defaults, Filters, tiers } from './types';

export function FiltersModal({ initial, onApply, closeModal }: {
  initial: Filters; onApply: (value: Filters) => void; closeModal?: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  return (
    <ConfirmModal
      strTitle="Filter charts"
      strOKButtonText="Apply filters"
      onOK={() => { onApply(draft); closeModal?.(); }}
      onCancel={closeModal}
      closeModal={closeModal}
    >
      <DropdownItem
        label="Difficulty" menuLabel="Chart difficulty"
        rgOptions={[{ data: 'all', label: 'All difficulties' }, ...tiers.map(([label, data]) => ({ label, data }))]}
        selectedOption={draft.difficulty}
        onChange={({ data }) => setDraft(value => ({ ...value, difficulty: data }))}
      />
      <SliderField
        label="Minimum rating" value={draft.minimum} min={0} max={99} step={1}
        showValue editableValue minimumDpadGranularity={1}
        onChange={minimum => setDraft(value => ({ ...value, minimum, maximum: Math.max(minimum, value.maximum) }))}
      />
      <SliderField
        label="Maximum rating" value={draft.maximum} min={0} max={99} step={1}
        showValue editableValue minimumDpadGranularity={1}
        onChange={maximum => setDraft(value => ({ ...value, maximum, minimum: Math.min(maximum, value.minimum) }))}
      />
      <p>A song must have a chart in the selected difficulty and rating range. With all difficulties selected, any matching chart qualifies.</p>
      <DialogButton onClick={() => setDraft({ ...defaults, sort: initial.sort })}>Reset filters</DialogButton>
    </ConfirmModal>
  );
}
