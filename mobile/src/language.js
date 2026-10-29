// Shared language labels + recipe icons for the farmer UI.
export const LANGUAGES = [
  { code: 'pidgin', label: '🇳🇬 Pidgin' },
  { code: 'hausa', label: '🇳🇬 Hausa' },
  { code: 'yoruba', label: '🇳🇬 Yoruba' },
  { code: 'english', label: '🇬🇧 English' },
];

// Crop picker: what the farmer is photographing + how to frame it.
// The hint is a WEAK prior (backend crop guard stays authoritative).
export const CROPS = [
  { code: null, label: '🤷 Auto-detect', emoji: '🤷', tip: 'Fill the frame with one affected leaf.' },
  { code: 'cassava', label: 'Cassava', emoji: '🥔', tip: 'Show the finger-like lobes spreading from one point.' },
  { code: 'maize', label: 'Maize', emoji: '🌽', tip: 'Frame one long blade with its center rib visible.' },
  { code: 'tomato', label: 'Tomato', emoji: '🍅', tip: 'Get close on one small leaflet with spots.' },
  { code: 'yam', label: 'Yam', emoji: '🍠', tip: 'Capture the whole big arrowhead leaf.' },
  { code: 'cowpea', label: 'Cowpea', emoji: '🫛', tip: 'Include all 3 round leaflets on the stalk.' },
  { code: 'sorghum', label: 'Sorghum', emoji: '🌾', tip: 'Frame the broad blade and pale center rib.' },
  { code: 'rice', label: 'Rice', emoji: '🍚', tip: 'Hold steady on the narrow ribbon leaf.' },
  { code: 'pepper', label: 'Pepper', emoji: '🌶️', tip: 'Focus one small glossy leaf.' },
  { code: 'okra', label: 'Okra', emoji: '🥬', tip: 'Show the coarse 5-lobed leaf shape.' },
  { code: 'groundnut', label: 'Groundnut', emoji: '🥜', tip: 'Include all 4 small oval leaflets.' },
  { code: 'sweet_potato', label: 'Sweet potato', emoji: '🍠', tip: 'Show the heart-shaped leaf and veins.' },
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
  if (d.includes('rust')) return { icon: '🟠', title: `${cap(crop)} Rust Spots` };
  if (d.includes('blast')) return { icon: '💥', title: `${cap(crop)} Blast Lesions` };
  if (d.includes('spot')) return { icon: '🔴', title: `${cap(crop)} Leaf Spots` };
  if (d.includes('mildew')) return { icon: '⚪', title: `${cap(crop)} White Mildew` };
  if (d.includes('aphid')) return { icon: '🪲', title: 'Tiny insects on leaf' };
  if (d.includes('virus') || d.includes('rosette') || d.includes('streak') || d.includes('curl')) {
    return { icon: '🦠', title: `${cap(crop)} Virus Signs` };
  }
  if (d.includes('smut')) return { icon: '⚫', title: `${cap(crop)} Smut Heads` };
  if (d.includes('anthracnose')) return { icon: '🟤', title: `${cap(crop)} Dark Spots` };
  if (d.includes('healthy')) return { icon: '💚', title: 'Leaf dey healthy!' };
  return { icon: '🔍', title: disease || 'Leaf sickness' };
}

function cap(s) {
  s = String(s || '');
  return s.charAt(0).toUpperCase() + s.slice(1);
}
