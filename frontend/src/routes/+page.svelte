<script>
	import { onMount } from 'svelte';

	const MAX_FILES = 20;
	const MAX_SIZE = 50 * 1024 * 1024;

	// Theme
	let dark = $state(true);
	function toggleTheme() {
		dark = !dark;
		document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
		localStorage.setItem('mubadal-theme', dark ? 'dark' : 'light');
	}
	onMount(() => {
		const saved = localStorage.getItem('mubadal-theme');
		if (saved === 'light') { dark = false; document.documentElement.setAttribute('data-theme', 'light'); }
	});

	let files = $state([]);
	let converting = $state(false);
	let progress = $state({ done: 0, total: 0 });
	let result = $state(null);   // { type, taskId?, taskIds?, detail }
	let toasts = $state([]);

	function fmt(bytes) {
		if (bytes < 1024) return bytes + ' B';
		if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
		return (bytes / 1048576).toFixed(1) + ' MB';
	}

	function toast(msg, type = 'error') {
		const id = Date.now();
		toasts = [...toasts, { id, msg, type }];
		setTimeout(() => { toasts = toasts.filter(t => t.id !== id); }, 4000);
	}

	function addFiles(incoming) {
		for (const f of incoming) {
			if (!f.name.toLowerCase().endsWith('.pptx')) { toast(`${f.name} is not .pptx`); continue; }
			if (f.size > MAX_SIZE) { toast(`${f.name} exceeds 50 MB`); continue; }
			if (files.some(x => x.name === f.name && x.size === f.size)) continue;
			if (files.length >= MAX_FILES) { toast(`Max ${MAX_FILES} files`); break; }
			files = [...files, f];
		}
		result = null;
	}

	function remove(idx) {
		files = files.filter((_, i) => i !== idx);
	}

	function clear() {
		files = [];
		result = null;
	}

	// Drag & drop
	let dragover = $state(false);
	function onDrop(e) {
		e.preventDefault();
		dragover = false;
		if (e.dataTransfer?.files.length) addFiles(Array.from(e.dataTransfer.files));
	}

	// File input
	let fileInput;
	function browse() { fileInput?.click(); }
	function onFileSelect(e) {
		if (e.target.files.length) { addFiles(Array.from(e.target.files)); e.target.value = ''; }
	}

	// Poll
	async function pollBatch(taskIds) {
		const total = taskIds.length;
		while (true) {
			await new Promise(r => setTimeout(r, 800));
			const res = await fetch('/api/tasks/status', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(taskIds)
			});
			const data = await res.json();
			const done = data.tasks.filter(t => t.state === 'SUCCESS' || t.state === 'FAILURE').length;
			progress = { done, total };
			if (done === total) {
				const ok = data.tasks.filter(t => t.state === 'SUCCESS');
				const fail = data.tasks.filter(t => t.state === 'FAILURE');
				return { ok, fail };
			}
		}
	}

	async function pollSingle(taskId) {
		while (true) {
			await new Promise(r => setTimeout(r, 800));
			const res = await fetch(`/api/task/${taskId}`);
			const data = await res.json();
			if (data.state === 'SUCCESS') return data.result;
			if (data.state === 'FAILURE') throw new Error(data.error || 'Failed');
		}
	}

	async function convert() {
		if (!files.length || converting) return;
		converting = true;
		result = null;
		progress = { done: 0, total: files.length };

		try {
			const batch = files.length > 1;
			if (!batch) {
				const fd = new FormData();
				fd.append('file', files[0]);
				const res = await fetch('/api/convert', { method: 'POST', body: fd });
				if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Upload failed');
				const { task_id } = await res.json();
				const r = await pollSingle(task_id);
				if (r.status !== 'success') throw new Error(r.error || 'Conversion failed');
				progress = { done: 1, total: 1 };
				result = { type: 'single', taskId: task_id, detail: `${r.filename} — ${fmt(r.size)}` };
			} else {
				const fd = new FormData();
				files.forEach(f => fd.append('files', f));
				const res = await fetch('/api/convert-batch', { method: 'POST', body: fd });
				if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Upload failed');
				const { tasks } = await res.json();
				const ids = tasks.map(t => t.task_id);
				const { ok, fail } = await pollBatch(ids);
				const totalSize = ok.reduce((s, t) => s + (t.result?.size || 0), 0);
				const detail = fail.length
					? `${ok.length} converted, ${fail.length} failed — ${fmt(totalSize)}`
					: `${ok.length} files — ${fmt(totalSize)}`;
				result = { type: 'batch', taskIds: ids, detail };
				if (fail.length) toast(`${fail.length} file(s) failed`);
			}
			toast('Done!', 'success');
		} catch (err) {
			toast(err.message);
		} finally {
			converting = false;
		}
	}

	async function download() {
		if (!result) return;
		try {
			let res;
			if (result.type === 'single') {
				res = await fetch(`/api/download/${result.taskId}`);
			} else {
				res = await fetch('/api/download-batch', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(result.taskIds)
				});
			}
			if (!res.ok) throw new Error('Download failed');
			const blob = await res.blob();
			const name = result.type === 'batch' ? 'converted_pdfs.zip' : 'converted.pdf';
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = name;
			a.click();
			URL.revokeObjectURL(url);
		} catch (err) {
			toast('Download failed: ' + err.message);
		}
	}
</script>

<div class="shell">
	<header class="header">
		<div class="header__row">
			<div>
				<h1>Mubadal</h1>
				<p>PPTX → PDF converter</p>
			</div>
			<button class="btn-theme" onclick={toggleTheme} title="Toggle theme">
				{dark ? '☀' : '☾'}
			</button>
		</div>
	</header>

	<main class="main">
		<!-- Drop zone -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="dropzone"
			class:dropzone--over={dragover}
			role="button"
			tabindex="0"
			ondragover={(e) => { e.preventDefault(); dragover = true; }}
			ondragleave={() => { dragover = false; }}
			ondrop={onDrop}
			onclick={browse}
			onkeydown={(e) => { if (e.key === 'Enter') browse(); }}
		>
			<span class="dropzone__icon">↑</span>
			<span>Drop <strong>.pptx</strong> files here or <span class="link">browse</span></span>
			<span class="dropzone__hint">Up to {MAX_FILES} files, {fmt(MAX_SIZE)} each</span>
		</div>
		<input type="file" accept=".pptx" multiple bind:this={fileInput} onchange={onFileSelect} hidden />

		<!-- File table -->
		{#if files.length > 0}
			<div class="file-section">
				<div class="file-section__header">
					<span class="file-section__count">{files.length} file{files.length > 1 ? 's' : ''}</span>
					<button class="btn-text btn-text--danger" onclick={clear}>Clear all</button>
				</div>
				<table class="file-table">
					<tbody>
						{#each files as file, idx}
							<tr class="file-row">
								<td class="file-row__name" title={file.name}>{file.name}</td>
								<td class="file-row__size">{fmt(file.size)}</td>
								<td class="file-row__action">
									<button class="btn-remove" onclick={() => remove(idx)} title="Remove">&times;</button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>

				<!-- Convert -->
				<div class="actions">
					<button
						class="btn-primary"
						onclick={convert}
						disabled={converting || files.length === 0}
					>
						{converting ? 'Converting…' : 'Convert to PDF'}
					</button>
				</div>

				<!-- Progress bar -->
				{#if converting}
					<div class="progress">
						<div class="progress__bar" style="width: {progress.total ? (progress.done / progress.total * 100) : 0}%"></div>
						<span class="progress__label">{progress.done} / {progress.total}</span>
					</div>
				{/if}
			</div>
		{/if}

		<!-- Result -->
		{#if result}
			<div class="result">
				<div class="result__info">
					<span class="result__check">✓</span>
					<span>{result.detail}</span>
				</div>
				<button class="btn-primary" onclick={download}>
					Download {result.type === 'batch' ? '.zip' : '.pdf'}
				</button>
			</div>
		{/if}
	</main>

	<footer class="footer">
		<span>Mubadal — converts .pptx to .pdf</span>
	</footer>
</div>

<!-- Toasts -->
<div class="toast-wrap">
	{#each toasts as t (t.id)}
		<div class="toast toast--{t.type}">{t.msg}</div>
	{/each}
</div>

<style>
	/* ── Layout ── */
	.shell {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		max-width: 640px;
		margin: 0 auto;
		padding: 48px 24px 24px;
	}

	.header {
		margin-bottom: 32px;
	}
	.header__row {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
	}
	.header h1 {
		font-size: 1.4rem;
		font-weight: 600;
		letter-spacing: -0.02em;
	}
	.header p {
		color: var(--text-secondary);
		font-size: 0.9rem;
		margin-top: 2px;
	}
	.btn-theme {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		width: 34px;
		height: 34px;
		font-size: 1.05rem;
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--text-secondary);
		transition: border-color 0.15s, background 0.15s;
	}
	.btn-theme:hover {
		border-color: var(--border-hover);
		background: var(--bg-hover);
	}

	.main { flex: 1; }

	.footer {
		margin-top: 48px;
		padding-top: 16px;
		border-top: 1px solid var(--border);
		color: var(--text-muted);
		font-size: 0.8rem;
	}

	/* ── Drop zone ── */
	.dropzone {
		border: 2px dashed var(--border-hover);
		border-radius: var(--radius);
		padding: 40px 24px;
		text-align: center;
		color: var(--text-secondary);
		font-size: 0.92rem;
		cursor: pointer;
		background: var(--bg-card);
		transition: border-color 0.15s, background 0.15s;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
		outline: none;
	}
	.dropzone:hover, .dropzone:focus-visible {
		border-color: var(--accent);
		background: var(--accent-light);
	}
	.dropzone--over {
		border-color: var(--accent);
		border-style: solid;
		background: var(--accent-light);
	}
	.dropzone__icon {
		font-size: 1.4rem;
		color: var(--text-muted);
		margin-bottom: 4px;
	}
	.dropzone__hint {
		font-size: 0.78rem;
		color: var(--text-muted);
	}
	.link {
		color: var(--accent);
		text-decoration: underline;
	}

	/* ── File section ── */
	.file-section {
		margin-top: 24px;
	}
	.file-section__header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 8px;
	}
	.file-section__count {
		font-size: 0.85rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	/* ── File table ── */
	.file-table {
		width: 100%;
		border-collapse: collapse;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		overflow: hidden;
		font-size: 0.88rem;
		background: var(--bg-card);
	}
	.file-row {
		border-bottom: 1px solid var(--border);
	}
	.file-row:last-child { border-bottom: none; }
	.file-row:hover { background: var(--bg-hover); }
	.file-row td { padding: 8px 12px; }
	.file-row__name {
		max-width: 0;
		width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.file-row__size {
		color: var(--text-muted);
		white-space: nowrap;
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.file-row__action { width: 32px; text-align: center; }

	/* ── Buttons ── */
	.btn-text {
		background: none;
		border: none;
		font-size: 0.82rem;
		padding: 2px 6px;
		border-radius: 4px;
	}
	.btn-text--danger { color: var(--danger); }
	.btn-text--danger:hover { background: var(--danger-light); }

	.btn-remove {
		background: none;
		border: none;
		font-size: 1.1rem;
		color: var(--text-muted);
		line-height: 1;
		padding: 2px 6px;
		border-radius: 4px;
	}
	.btn-remove:hover { color: var(--danger); background: var(--danger-light); }

	.btn-primary {
		background: var(--accent);
		color: #fff;
		border: none;
		padding: 9px 20px;
		border-radius: var(--radius);
		font-size: 0.88rem;
		font-weight: 500;
		transition: background 0.12s;
	}
	.btn-primary:hover:not(:disabled) { background: var(--accent-hover); }
	.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

	.actions {
		margin-top: 16px;
		display: flex;
		gap: 8px;
	}

	/* ── Progress ── */
	.progress {
		margin-top: 12px;
		height: 24px;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		position: relative;
		overflow: hidden;
	}
	.progress__bar {
		height: 100%;
		background: var(--accent);
		border-radius: var(--radius);
		transition: width 0.3s ease;
		min-width: 2px;
	}
	.progress__label {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
		mix-blend-mode: difference;
		font-variant-numeric: tabular-nums;
	}

	/* ── Result ── */
	.result {
		margin-top: 20px;
		padding: 14px 16px;
		border: 1px solid rgba(63, 185, 80, 0.25);
		background: var(--success-light);
		border-radius: var(--radius);
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
	}
	.result__info {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 0.88rem;
		min-width: 0;
	}
	.result__check {
		color: var(--success);
		font-weight: 700;
	}

	/* ── Toasts ── */
	.toast-wrap {
		position: fixed;
		bottom: 20px;
		right: 20px;
		display: flex;
		flex-direction: column;
		gap: 8px;
		z-index: 100;
	}
	.toast {
		padding: 10px 16px;
		border-radius: var(--radius);
		font-size: 0.84rem;
		color: #fff;
		animation: slidein 0.25s ease;
	}
	.toast--error { background: var(--danger); }
	.toast--success { background: var(--success); }
	@keyframes slidein {
		from { opacity: 0; transform: translateY(8px); }
		to { opacity: 1; transform: none; }
	}

	/* ── Responsive ── */
	@media (max-width: 480px) {
		.shell { padding: 32px 16px 16px; }
		.result { flex-direction: column; align-items: stretch; }
	}
</style>
