class Account:
    def __init__(self, name, threshold, message=None, number=None):
        assert name
        assert threshold
        self.name = name
        self.threshold = threshold
        self.message = message
        self.number = number

    def getName(self):
        return self.name

    def getThreshold(self):
        return self.threshold

    def getMessage(self):
        if not self.message:
            return ""
        return self.message

    def getNumber(self):
        if not self.number:
            return ""
        return self.number
