from werkzeug.security import generate_password_hash

# Cambia esta línea por la nueva contraseña que quieras asignar
nueva_contra = "nueva123"

# Generar hash
hash_generado = generate_password_hash(nueva_contra)

print("Este es el nuevo hash para la contraseña:")
print(hash_generado)
