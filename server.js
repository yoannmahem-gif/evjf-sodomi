const express = require('express');
const Database = require('better-sqlite3');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

const db = new Database(path.join(__dirname, 'evjf.db'));

db.exec(`
  CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author TEXT NOT NULL,
    question TEXT NOT NULL,
    done INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )
`);

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

app.get('/cartes', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'cartes.html'));
});

app.get('/api/questions', (req, res) => {
  const all = db.prepare('SELECT * FROM questions ORDER BY created_at ASC').all();
  res.json(all);
});

app.post('/api/questions', (req, res) => {
  const { author, question } = req.body;
  if (!author?.trim() || !question?.trim()) {
    return res.status(400).json({ error: 'Les deux champs sont requis.' });
  }
  const stmt = db.prepare('INSERT INTO questions (author, question) VALUES (?, ?)');
  const result = stmt.run(author.trim(), question.trim());
  res.json({
    id: result.lastInsertRowid,
    author: author.trim(),
    question: question.trim(),
    done: 0,
    created_at: new Date().toISOString()
  });
});

app.patch('/api/questions/:id/done', (req, res) => {
  db.prepare('UPDATE questions SET done = 1 WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

app.patch('/api/questions/:id/undone', (req, res) => {
  db.prepare('UPDATE questions SET done = 0 WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

app.delete('/api/questions/:id', (req, res) => {
  db.prepare('DELETE FROM questions WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

app.listen(PORT, () => {
  console.log(`\n✨ EVJF App lancée !`);
  console.log(`\n  Lien participants : http://localhost:${PORT}/`);
  console.log(`  Lien mariée       : http://localhost:${PORT}/cartes`);
  console.log(`\nAppuyez sur Ctrl+C pour arrêter.\n`);
});
