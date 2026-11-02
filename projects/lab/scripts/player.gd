extends CharacterBody3D

const SPEED := 3.0

func _physics_process(delta: float) -> void:
	var movement := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	velocity.x = movement.x * SPEED
	velocity.z = movement.y * SPEED
	if not is_on_floor():
		velocity.y -= 9.81 * delta
	else:
		velocity.y = 0.0
	move_and_slide()
