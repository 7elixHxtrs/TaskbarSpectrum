from taskbar_spectrum_app import make_icon_image

make_icon_image(256).save(
    "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
)
print("icon.ico creado")
