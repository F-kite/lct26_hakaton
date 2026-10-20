import { findMatch } from "../../lib/history";

interface Props {
  text: string;
  input: string;
}

export default function Highlight({ text, input }: Props) {
  const idx = findMatch(text, input);
  if (idx === -1) return <span className="text-neutral-950">{text}</span>;
  const end = idx + input.trim().length;
  return (
    <span className="text-neutral-500">
      {text.slice(0, idx)}
      <span className="text-neutral-950">{text.slice(idx, end)}</span>
      {text.slice(end)}
    </span>
  );
}
