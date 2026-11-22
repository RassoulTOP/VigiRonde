import { useSyncExternalStore } from 'react';

import { outbox } from './outbox';

export function useOutbox() {
  return useSyncExternalStore(outbox.subscribe, outbox.get);
}
