(() => {
	document.querySelectorAll(".kanban-card[draggable]").forEach((card) => {
		card.addEventListener("dragstart", function (e) {
			e.dataTransfer.setData("text/plain", this.dataset.taskId);
			this.classList.add("dragging");
		});
		card.addEventListener("dragend", function () {
			this.classList.remove("dragging");
		});
	});
	document.querySelectorAll(".kanban-cards").forEach((col) => {
		col.addEventListener("dragover", function (e) {
			e.preventDefault();
			this.classList.add("drag-over");
		});
		col.addEventListener("dragleave", function () {
			this.classList.remove("drag-over");
		});
		col.addEventListener("drop", function (e) {
			e.preventDefault();
			this.classList.remove("drag-over");
			const taskId = e.dataTransfer.getData("text/plain");
			const stageId = this.closest(".kanban-column").dataset.stageId;
			if (!taskId || !stageId) return;
			fetch("/projects/api/move-task", {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"X-CSRFToken": document.querySelector('meta[name="csrf-token"]').content,
				},
				body: JSON.stringify({
					task_id: parseInt(taskId, 10),
					stage_id: parseInt(stageId, 10),
				}),
			})
				.then((r) => r.json())
				.then((d) => {
					if (d.success) location.reload();
				})
				.catch(() => location.reload());
		});
	});
})();
