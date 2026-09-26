// ═══════════════════════════════════════════════════════════════
// ByteToBite — OCR slip reader (Tesseract.js)
//
// Reads Indian Mandi / weighbridge slips and returns structured fields.
// Used by: page1.html (Kisan Seller Portal)
// Depends on: Tesseract.js CDN (loaded in page1.html <head>)
//
// Public API (window.ByteToBiteOCR):
//   readSlip(file)    → { rawText, confidence, weightKg, date, mandiName, traderName, category, moisture }
//   terminate()       → release the Tesseract worker
//   guessCategory(text)
//   guessWeight(text)
//   _categories       → exported category list (mirrors backend CATEGORIES)
// ═══════════════════════════════════════════════════════════════

(function () {
    'use strict';

    // ─────────────────────────────────────────────
    // SHARED CATEGORY LIST — keep in sync with backend
    // ─────────────────────────────────────────────
    const CATEGORIES = [
        'MUSHROOM_SUBSTRATE',
        'CITRUS_POMACE',
        'SILICA_SAND',
        'PLANT_FIBER',
        'COOKED_SURPLUS',
        'BIO_MASS',
        'OTHER',
    ];

    // Keyword hints for auto-classification (English + Hindi)
    const CATEGORY_HINTS = {
        MUSHROOM_SUBSTRATE: ['mushroom', 'spent substrate', 'fungus', 'खुम्ब', 'मशरूम'],
        CITRUS_POMACE: ['citrus', 'orange', 'kinnow', 'pomace', 'peel', 'नींबू', 'संतरा', 'छिलका'],
        SILICA_SAND: ['silica', 'sand', 'foundry', 'mould', 'रेत', 'बालू'],
        PLANT_FIBER: ['bagasse', 'sugarcane', 'fiber', 'fibre', 'bagas', 'गन्ना', 'बगास'],
        COOKED_SURPLUS: ['cooked', 'rice', 'dal', 'khichdi', 'surplus', 'canteen', 'पका', 'खाना'],
        BIO_MASS: ['biomass', 'straw', 'residue', 'leaf', 'leaves', 'पत्ता', 'अवशेष', 'पराली'],
    };

    // ─────────────────────────────────────────────
    // WORKER LIFECYCLE
    // ─────────────────────────────────────────────
    let worker = null;
    let readyPromise = null;

    async function ensureWorker() {
        if (readyPromise) return readyPromise;
        readyPromise = (async () => {
            if (!window.Tesseract) {
                throw new Error('Tesseract.js not loaded — check the script tag in <head>');
            }
            // English + Hindi — Indian slips mix both.
            worker = await window.Tesseract.createWorker('eng+hin', 1, {
                logger: (m) => {
                    if (typeof window._ocrProgress === 'function') {
                        try { window._ocrProgress(m); } catch (e) { }
                    }
                },
            });
            return worker;
        })();
        return readyPromise;
    }

    // ─────────────────────────────────────────────
    // FIELD PARSERS
    // ─────────────────────────────────────────────

    // Weight: "Net Weight 1250 kg", "तौल: 1250", "1250.50 kg"
    function pickWeight(text) {
        const patterns = [
            /(?:net\s*weight|weight|तौल|वजन|कुल\s*वजन)[^\d]{0,12}(\d{2,6}(?:[.,]\d{1,2})?)/i,
            /(\d{2,6}(?:[.,]\d{1,2})?)\s*(?:kg|kgs|कि\.?ग्रा\.?|किलो)/i,
            /(\d{2,6}(?:[.,]\d{1,2})?)\s*(?:qtl|quintal|क्विंटल)/i,
        ];
        for (const p of patterns) {
            const m = text.match(p);
            if (m) {
                let v = parseFloat(m[1].replace(',', '.'));
                if (/qtl|quintal|क्विंटल/i.test(m[0])) v *= 100;
                if (v >= 1 && v <= 100000) return Math.round(v);
            }
        }
        // Fallback: largest plausible number
        const nums = (text.match(/\d{2,6}(?:[.,]\d{1,2})?/g) || [])
            .map((s) => parseFloat(s.replace(',', '.')))
            .filter((n) => n >= 50 && n <= 50000);
        return nums.length ? Math.round(Math.max(...nums)) : null;
    }

    // Date: dd/mm/yyyy, yyyy-mm-dd, dd.mm.yy
    function pickDate(text) {
        const patterns = [
            /(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})/,
            /(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})/,
        ];
        for (const p of patterns) {
            const m = text.match(p);
            if (m) return m[0];
        }
        return new Date().toLocaleDateString('en-IN');
    }

    // Mandi name
    function pickMandi(text) {
        const m1 = text.match(/([A-Z][a-z]{2,})\s+(?:Mandi|मंडी|Market)/);
        if (m1) return m1[0].trim();
        const m2 = text.match(/(?:Mandi|मंडी|Market)[:\s]+([A-Z][A-Za-z]{2,})/);
        if (m2) return m2[1].trim() + ' Mandi';
        return null;
    }

    // Trader / firm
    function pickTrader(text) {
        const m = text.match(/(?:Trader|व्यापारी|Firm|Shop|आढ़तिया)[:\s]+([A-Z][A-Za-z\s&.,']{2,40})/);
        return m ? m[1].trim().replace(/[.,]$/, '') : null;
    }

    // Moisture percent — often printed as "Moisture 14.2%" or "नमी 14%"
    function pickMoisture(text) {
        const m = text.match(/(?:moisture|नमी)[^\d]{0,10}(\d{1,2}(?:[.,]\d{1,2})?)\s*%?/i);
        if (m) {
            const v = parseFloat(m[1].replace(',', '.'));
            if (v >= 0 && v <= 100) return v;
        }
        return null;
    }

    // Auto-classify by keyword match
    function pickCategory(text) {
        const lower = text.toLowerCase();
        let best = null;
        let bestScore = 0;
        for (const [cat, hints] of Object.entries(CATEGORY_HINTS)) {
            let score = 0;
            hints.forEach((h) => {
                if (lower.includes(h.toLowerCase())) score++;
            });
            if (score > bestScore) {
                bestScore = score;
                best = cat;
            }
        }
        return bestScore > 0 ? best : null;
    }

    // ─────────────────────────────────────────────
    // PUBLIC API
    // ─────────────────────────────────────────────
    window.ByteToBiteOCR = {
        _categories: CATEGORIES.slice(),

        /**
         * Read a slip photo and return structured fields.
         * @param {File|Blob} file — image file from <input type="file">
         */
        async readSlip(file) {
            if (!file) throw new Error('No file provided to readSlip()');
            const w = await ensureWorker();
            const result = await w.recognize(file);
            const text = (result.data && result.data.text) || '';
            const confidence = (result.data && result.data.confidence) || 0;

            const trimmed = text.trim();

            const weightKg = pickWeight(trimmed);
            const date = pickDate(trimmed);
            const mandiName = pickMandi(trimmed);
            const traderName = pickTrader(trimmed);
            const moisture = pickMoisture(trimmed);
            const category = pickCategory(trimmed);

            return {
                rawText: trimmed,
                confidence: Math.round(confidence),
                weightKg,
                date,
                mandiName,
                traderName,
                moisture,
                category,
            };
        },

        /**
         * Free the Tesseract worker. Call on unmount / logout if needed.
         */
        async terminate() {
            if (worker) {
                try { await worker.terminate(); } catch (e) { }
                worker = null;
                readyPromise = null;
            }
        },

        /**
         * Utility: guess a category from arbitrary text.
         */
        guessCategory(text) {
            return pickCategory(String(text || ''));
        },

        /**
         * Utility: pull just weight from arbitrary text.
         */
        guessWeight(text) {
            return pickWeight(String(text || ''));
        },
    };
})();