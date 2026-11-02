extends SceneTree

var checks: Array[Dictionary] = []
var report_path := "user://gold-path.json"

func _init() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--report="):
			report_path = argument.trim_prefix("--report=")
	_run.call_deferred()

func _expect(condition: bool, title: String) -> void:
	checks.append({"name": title, "passed": condition})
	print("PASS " if condition else "FAIL ", title)

func _press(action: String) -> void:
	Input.action_press(action)
	await process_frame
	await process_frame
	Input.action_release(action)
	await process_frame
	await physics_frame

func _run() -> void:
	var scene = load("res://scenes/lab.tscn")
	if scene == null:
		quit(1)
		return
	var lab = scene.instantiate()
	root.add_child(lab)
	await physics_frame
	await physics_frame
	_expect(not lab.door_open and not lab.power_on, "normal startup is unpowered and closed")
	_expect(not lab.run_experiment(), "experiment cannot run without prerequisites")
	var query := PhysicsRayQueryParameters3D.create(Vector3(0, 1, 2.5), Vector3(0, 1, 1))
	var space: PhysicsDirectSpaceState3D = lab.get_world_3d().direct_space_state
	_expect(not space.intersect_ray(query).is_empty(), "closed door has world-space collision")
	await _press("interact")
	await physics_frame
	_expect(lab.door_open, "interaction input opens door")
	_expect(space.intersect_ray(query).is_empty(), "open door clears world-space collision")
	await _press("interact")
	await physics_frame
	_expect(not lab.door_open and not space.intersect_ray(query).is_empty(), "closing restores collision")
	await _press("interact")
	await _press("power")
	await _press("experiment")
	_expect(lab.experiment_complete, "real action sequence completes reference experiment")
	_expect(absf(lab.last_period_seconds - 2.00606668) < 0.00001, "analytic reference matches independent expected value")
	var start: Vector3 = lab.player.global_position
	Input.action_press("move_right")
	for frame in range(10):
		await physics_frame
	Input.action_release("move_right")
	_expect(lab.player.global_position.x > start.x + 0.1, "movement input changes world-space player position")
	var save_path := report_path.get_base_dir().path_join("lab-save.json")
	_expect(lab.save_state(save_path), "save writes successfully")
	lab.set_power(false)
	lab.set_door(false)
	_expect(lab.restore_state(save_path), "saved state restores successfully")
	_expect(lab.power_on and lab.door_open and lab.experiment_complete, "save/load preserves outcomes")
	_expect(not lab.restore_state(save_path + ".missing"), "missing save is rejected")
	var generated_expected := FileAccess.file_exists("res://assets/generated/bench.glb")
	_expect(not generated_expected or lab.generated_bench_loaded, "available Blender asset imports into running scene")
	var passed := true
	for check in checks:
		passed = passed and check["passed"]
	var file := FileAccess.open(report_path, FileAccess.WRITE)
	if file == null:
		quit(1)
		return
	file.store_string(JSON.stringify({"status": "passed" if passed else "failed",
		"checks": checks, "generated_asset_expected": generated_expected,
		"human_approval": "pending", "visual_review": "not_performed_headless"}, "  "))
	file.close()
	lab.queue_free()
	await process_frame
	quit(0 if passed else 1)
