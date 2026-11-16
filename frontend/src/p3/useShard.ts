import { useEffect, useState } from "react";

export function useShard<Ref, Value>(
  ref: Ref | undefined, read: (ref: Ref) => Promise<Value>,
) {
  const [resolved, setResolved] = useState<{
    ref: Ref;
    read: typeof read;
    result: { value: Value } | { error: string };
  } | null>(null);

  useEffect(() => {
    if (ref === undefined) return;
    let current = true;
    void read(ref).then(
      (value) => { if (current) setResolved({ ref, read, result: { value } }); },
      (cause: unknown) => {
        if (current) setResolved({
          ref, read, result: { error: cause instanceof Error ? cause.message : "Could not verify the selected shard." },
        });
      },
    );
    return () => { current = false; };
  }, [ref, read]);
  return resolved?.ref === ref && resolved?.read === read ? resolved.result : null;
}
