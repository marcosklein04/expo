try:
    import MySQLdb  # noqa: F401
except Exception:
    try:
        import pymysql

        pymysql.install_as_MySQLdb()
    except Exception:
        pass
