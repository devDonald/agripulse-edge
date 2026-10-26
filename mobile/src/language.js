// Shared language labels + recipe icons for the farmer UI.
export const LANGUAGES = [
  { code: 'pidgin', label: '🇳🇬 Pidgin' },
  { code: 'hausa', label: '🇳🇬 Hausa' },
  { code: 'yoruba', label: '🇳🇬 Yoruba' },
  { code: 'english', label: '🇬🇧 English' },
];

export const STRINGS = {
  pidgin: {
    snap: '📸 Snap Sick Leaf', history: '📂 My Farm History', play: '🔊 Play Voice Advice in Nigerian Pidgin',
    save: '💾 Save to Offline History', howTo: 'How to treat am (3 cheap things)',
  },
  hausa: {
    snap: '📸 Dauki Hoton Ganye', history: '📂 Tarihin Gonata', play: '🔊 Saurari Shawara a Hausa',
    save: '💾 Ajiye a Waya', howTo: 'Yadda za ka magance ta (abubuwa 3)',
  },
  yoruba: {
    snap: '📸 Ya Fọ́tọ̀ Ewé Àrùn', history: '📂 Ìtàn Ọ̀kọ̀ Mi', play: '🔊 Gbọ́ Ìmọ̀ràn ní Yorùbá',
    save: '💾 Fi Pamọ́', howTo: 'Báwo ni lá ṣe tọ́jú rẹ̀ (nǹkan mẹ́ta)',
  },
  english: {
    snap: '📸 Snap Sick Leaf', history: '📂 My Farm History', play: '🔊 Play Voice Advice in English',
    save: '💾 Save to Offline History', howTo: 'How to treat it (3 cheap remedies)',
  },
};

export const RECIPE_ICONS = ['🌿', '🪵', '🧼'];

export function simpleName(crop, disease) {
  const d = (disease || '').toLowerCase();
  if (d.includes('mosaic')) return { icon: '🟡', title: `${cap(crop)} Yellow Mosaic` };
  if (d.includes('armyworm')) return { icon: '🐛', title: 'Worm don chop leaf' };
  if (d.includes('blight')) return { icon: '🟤', title: `${cap(crop)} Brown Spots` };
  if (d.includes('healthy')) return { icon: '💚', title: 'Leaf dey healthy!' };
  return { icon: '🔍', title: disease || 'Leaf sickness' };
}

function cap(s) {
  s = String(s || '');
  return s.charAt(0).toUpperCase() + s.slice(1);
}
