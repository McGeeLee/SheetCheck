"""Safe, stable error codes; never interpolate business values in errors."""


class SheetCheckError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class InputError(SheetCheckError):
    pass


class IntegrityError(SheetCheckError):
    pass


class ExportError(SheetCheckError):
    pass


PROBLEM_HELP = {
    "ID_MISSING": "请从原系统补充文本业务编号。",
    "ID_NOT_TEXT": "请重新导出文本编号；改变显示格式无法恢复前导零或丢失的精度。",
    "ID_WHITESPACE": "请修正源文件中编号首尾空白；程序不静默修剪。",
    "ID_CONTROL_CHARACTER": "请移除源文件编号中的控制或不可见格式字符。",
    "ID_TOO_LONG": "编号最多 128 个 Unicode 字符。",
    "AMOUNT_MISSING": "请补充非负且最多两位小数的金额；零有效。",
    "AMOUNT_TYPE": "请从可信来源导出普通数值或十进制文本金额。",
    "AMOUNT_FORMAT": "请使用无符号、无千分位、非科学计数法的十进制金额。",
    "AMOUNT_PRECISION": "金额最多两位小数；程序不会四舍五入。",
    "AMOUNT_LIMIT": "单笔金额不得超过 999999999.99。",
    "DUPLICATE_ID": "同编号在至少一侧重复；请确认源数据，当前版本不合并收款。",
    "BLOCKED_ID": "同编号关联行存在数据问题；两侧全部隔离，请修正源文件。",
}
