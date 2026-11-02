extends Node3D

const PlayerScript = preload("res://scripts/player.gd")
const PENDULUM_LENGTH_M := 1.0
const GRAVITY_M_S2 := 9.81

var door_open := false
var power_on := false
var experiment_complete := false
var last_period_seconds := 0.0
var player: CharacterBody3D
var door_pivot: Node3D
var door_collision: CollisionShape3D
var power_material: StandardMaterial3D
var pendulum: Node3D
var status_label: Label
var result_label: Label
var asset_label: Label
var generated_bench_loaded := false
var elapsed := 0.0

func _ready() -> void:
	_bind_actions()
	_build_room()
	_build_player()
	_build_interface()
	_update_interface()
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--capture="):
			_capture.call_deferred(argument.trim_prefix("--capture="))
		elif argument.begins_with("--smoke-report="):
			_export_smoke.call_deferred(argument.trim_prefix("--smoke-report="))

func _bind_actions() -> void:
	var bindings := {
		"interact": KEY_E, "power": KEY_P, "experiment": KEY_R,
		"move_left": KEY_A, "move_right": KEY_D,
		"move_forward": KEY_W, "move_back": KEY_S,
	}
	for action in bindings:
		if not InputMap.has_action(action):
			InputMap.add_action(action)
			var event := InputEventKey.new()
			event.physical_keycode = bindings[action]
			InputMap.action_add_event(action, event)

func _material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.7
	return material

func _box(parent: Node3D, title: String, at: Vector3, dimensions: Vector3,
		color: Color, solid := false) -> Node3D:
	var holder: Node3D
	if solid:
		holder = StaticBody3D.new()
	else:
		holder = Node3D.new()
	holder.name = title
	holder.position = at
	parent.add_child(holder)
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = dimensions
	mesh.mesh = box
	mesh.material_override = _material(color)
	holder.add_child(mesh)
	if solid:
		var collision := CollisionShape3D.new()
		var shape := BoxShape3D.new()
		shape.size = dimensions
		collision.shape = shape
		holder.add_child(collision)
	return holder

func _label3d(text: String, at: Vector3, size := 40) -> void:
	var label := Label3D.new()
	label.text = text
	label.position = at
	label.font_size = size
	label.pixel_size = 0.005
	label.modulate = Color("71f0cf")
	add_child(label)

func _build_room() -> void:
	var environment := WorldEnvironment.new()
	var settings := Environment.new()
	settings.background_mode = Environment.BG_COLOR
	settings.background_color = Color("0b1224")
	settings.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	settings.ambient_light_color = Color("afcfe3")
	settings.ambient_light_energy = 0.6
	environment.environment = settings
	add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-55, -30, 0)
	light.light_energy = 1.4
	light.shadow_enabled = true
	add_child(light)
	var camera := Camera3D.new()
	camera.position = Vector3(8, 9, 12)
	add_child(camera)
	camera.look_at(Vector3(0, 0.5, 0))
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 13.2
	camera.current = true
	_box(self, "Floor", Vector3(0, -0.15, 0), Vector3(10, 0.3, 8), Color("18283d"), true)
	_box(self, "BackWall", Vector3(0, 1.25, -4), Vector3(10, 2.5, 0.2), Color("24354a"), true)
	_box(self, "LeftWall", Vector3(-5, 0.5, 0), Vector3(0.2, 1, 8), Color("24354a"), true)
	_box(self, "RightWall", Vector3(5, 0.5, 0), Vector3(0.2, 1, 8), Color("24354a"), true)
	for x in range(-4, 5):
		_box(self, "FloorLine", Vector3(x, 0.006, 0), Vector3(0.015, 0.01, 8), Color("294356"))
	for z in range(-3, 4):
		_box(self, "FloorLine", Vector3(0, 0.007, z), Vector3(10, 0.01, 0.015), Color("294356"))
	_label3d("N O V A N O D E   /   L A B  0 1", Vector3(0, 2, -3.85), 65)
	_label3d("POWER", Vector3(-2.5, 1.8, -1.6))
	_label3d("ANALYTIC REFERENCE", Vector3(2.2, 2.5, -1.6), 30)
	for x in [-2.5, 2.2]:
		var bench_at := Vector3(x, 0, -1.6)
		if ResourceLoader.exists("res://assets/generated/bench.glb"):
			var bench = load("res://assets/generated/bench.glb").instantiate()
			bench.position = bench_at
			add_child(bench)
			generated_bench_loaded = true
		else:
			_box(self, "GreyboxBench", bench_at + Vector3(0, 0.45, 0),
				Vector3(1.6, 0.9, 0.7), Color("237984"))
		# Collision is intentionally separate from the decorative interchange asset.
		var body := StaticBody3D.new()
		body.position = bench_at + Vector3(0, 0.45, 0)
		var collision := CollisionShape3D.new()
		var shape := BoxShape3D.new()
		shape.size = Vector3(1.6, 0.9, 0.7)
		collision.shape = shape
		body.add_child(collision)
		add_child(body)
	var power := _box(self, "PowerCell", Vector3(-2.5, 1.2, -1.6),
		Vector3(0.45, 0.55, 0.45), Color("f9a45a"))
	power_material = (power.get_child(0) as MeshInstance3D).material_override
	pendulum = Node3D.new()
	pendulum.position = Vector3(2.2, 2.25, -1.6)
	add_child(pendulum)
	_box(pendulum, "Rod", Vector3(0, -0.5, 0), Vector3(0.04, 1, 0.04), Color("71f0cf"))
	_box(pendulum, "Bob", Vector3(0, -1, 0), Vector3(0.22, 0.22, 0.22), Color("f9a45a"))
	door_pivot = Node3D.new()
	door_pivot.position = Vector3(-0.8, 0, 1.8)
	add_child(door_pivot)
	var door := _box(door_pivot, "Door", Vector3(0.8, 1, 0),
		Vector3(1.6, 2, 0.15), Color("398c92"), true)
	door_collision = door.get_child(1) as CollisionShape3D
	for x in [-0.95, 0.95]:
		_box(self, "DoorFrame", Vector3(x, 1, 1.8), Vector3(0.15, 2, 0.25), Color("415c77"), true)
	_box(self, "DoorHeader", Vector3(0, 2.05, 1.8), Vector3(2.05, 0.15, 0.25), Color("71f0cf"))

func _build_player() -> void:
	player = CharacterBody3D.new()
	player.name = "Player"
	player.set_script(PlayerScript)
	player.position = Vector3(0, 0.55, 3)
	var collision := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.23
	capsule.height = 1.0
	collision.shape = capsule
	player.add_child(collision)
	var mesh := MeshInstance3D.new()
	var visual := CapsuleMesh.new()
	visual.radius = 0.23
	visual.height = 1.0
	mesh.mesh = visual
	mesh.material_override = _material(Color("71f0cf"))
	player.add_child(mesh)
	add_child(player)

func _build_interface() -> void:
	var canvas := CanvasLayer.new()
	add_child(canvas)
	var panel := PanelContainer.new()
	panel.position = Vector2(24, 24)
	panel.custom_minimum_size = Vector2(440, 0)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.035, 0.065, 0.11, 0.95)
	style.content_margin_left = 18
	style.content_margin_right = 18
	style.content_margin_top = 14
	style.content_margin_bottom = 14
	style.border_width_left = 3
	style.border_color = Color("71f0cf")
	panel.add_theme_stylebox_override("panel", style)
	canvas.add_child(panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 10)
	panel.add_child(column)
	var title := Label.new()
	title.text = "NOVANODE / STUDIO LAB"
	title.add_theme_font_size_override("font_size", 23)
	column.add_child(title)
	var subtitle := Label.new()
	subtitle.text = "PIPELINE VERTICAL SLICE  /  01"
	subtitle.modulate = Color("71f0cf")
	column.add_child(subtitle)
	status_label = Label.new()
	column.add_child(status_label)
	result_label = Label.new()
	column.add_child(result_label)
	var buttons := HBoxContainer.new()
	column.add_child(buttons)
	for spec in [["E / Door", toggle_door], ["P / Power", toggle_power], ["R / Run", run_experiment]]:
		var button := Button.new()
		button.text = spec[0]
		button.pressed.connect(spec[1])
		button.focus_mode = Control.FOCUS_NONE
		buttons.add_child(button)
	asset_label = Label.new()
	asset_label.text = "Asset: Blender GLB" if generated_bench_loaded else "Asset: greybox fallback"
	asset_label.modulate = Color("98b3c8")
	column.add_child(asset_label)
	var footer := Label.new()
	footer.text = "WASD: move  |  E: door  |  P: power  |  R: run\nReference formula only. Not a validated physics simulation."
	footer.position = Vector2(24, 730)
	footer.add_theme_font_size_override("font_size", 17)
	canvas.add_child(footer)

func _process(delta: float) -> void:
	if Input.is_action_just_pressed("interact"):
		toggle_door()
	if Input.is_action_just_pressed("power"):
		toggle_power()
	if Input.is_action_just_pressed("experiment"):
		run_experiment()
	door_pivot.rotation.y = lerp_angle(door_pivot.rotation.y, -PI / 2 if door_open else 0.0, delta * 8)
	elapsed += delta
	pendulum.rotation.z = sin(elapsed * TAU / maxf(last_period_seconds, 0.1)) * 0.15 if experiment_complete and power_on else 0.0

func toggle_door() -> void:
	set_door(not door_open)

func set_door(open: bool) -> void:
	door_open = open
	door_collision.set_deferred("disabled", open)
	_update_interface()

func toggle_power() -> void:
	set_power(not power_on)

func set_power(on: bool) -> void:
	power_on = on
	power_material.albedo_color = Color("71f0cf") if on else Color("f9a45a")
	_update_interface()

func run_experiment() -> bool:
	if not door_open or not power_on:
		result_label.text = "Open the door and enable power first."
		return false
	# Small-angle analytical period, not a measurement from the visual animation.
	last_period_seconds = TAU * sqrt(PENDULUM_LENGTH_M / GRAVITY_M_S2)
	experiment_complete = true
	_update_interface()
	return true

func _update_interface() -> void:
	if not is_instance_valid(status_label):
		return
	status_label.text = "Door: %s   /   Power: %s" % ["OPEN" if door_open else "CLOSED", "ON" if power_on else "OFF"]
	result_label.text = "T = 2π√(L/g) = %.4f s  /  L = 1 m" % last_period_seconds if experiment_complete else "Objective: open → power → run reference"

func save_state(path: String) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(JSON.stringify({"schema_version": 1, "door_open": door_open,
		"power_on": power_on, "experiment_complete": experiment_complete}))
	file.close()
	return true

func restore_state(path: String) -> bool:
	if not FileAccess.file_exists(path):
		return false
	var state = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not state is Dictionary or state.get("schema_version") != 1:
		return false
	for field in ["door_open", "power_on", "experiment_complete"]:
		if not state.get(field) is bool:
			return false
	set_door(state["door_open"])
	set_power(state["power_on"])
	experiment_complete = state["experiment_complete"]
	last_period_seconds = TAU * sqrt(PENDULUM_LENGTH_M / GRAVITY_M_S2) if experiment_complete else 0.0
	_update_interface()
	return true

func _capture(path: String) -> void:
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var error := get_viewport().get_texture().get_image().save_png(path)
	get_tree().quit(0 if error == OK else 1)

func _press(action: String) -> void:
	Input.action_press(action)
	await get_tree().process_frame
	await get_tree().process_frame
	Input.action_release(action)
	await get_tree().process_frame

func _export_smoke(path: String) -> void:
	await get_tree().physics_frame
	await _press("interact")
	await _press("power")
	await _press("experiment")
	var passed := door_open and power_on and experiment_complete and absf(last_period_seconds - 2.00606668) < 0.00001
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		get_tree().quit(1)
		return
	file.store_string(JSON.stringify({"status": "passed" if passed else "failed",
		"normal_startup": true, "generated_bench_loaded": generated_bench_loaded,
		"human_approval": "pending", "period_seconds": last_period_seconds}, "  "))
	file.close()
	get_tree().quit(0 if passed else 1)
