import {DToasterShowProps, Toaster} from '@dagster-io/ui';
import memoize from 'lodash/memoize';

// todo dish: Delete this after Cloud is updated.
export const SharedToaster = Toaster.create({position: 'top'}, document.body);

export const getSharedToaster = memoize(async () => {
  return await Toaster.asyncCreate({position: 'top'}, document.body);
});

export const showSharedToaster = async (config: DToasterShowProps) => {
  const toaster = await getSharedToaster();
  toaster.show(config);
};

export async function copyValue(event: React.MouseEvent<any>, value: string) {
  event.preventDefault();

  const el = document.createElement('textarea');
  document.body.appendChild(el);
  el.value = value;
  el.select();
  document.execCommand('copy');
  el.remove();

  await showSharedToaster({
    message: 'Copied to clipboard!',
    icon: 'copy_to_clipboard_done',
    intent: 'none',
  });
}
