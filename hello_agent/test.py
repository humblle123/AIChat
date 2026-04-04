class Person:
    def __init__(self, name, age):
        self.name = name
        self.age = age
    
    @classmethod
    def from_string(cls, data):
        """从字符串 'name,age' 创建实例"""
        name, age = data.split(',')
        return cls(name, int(age))
    
    @classmethod
    def from_dict(cls, data):
        """从字典创建实例"""
        return cls(data['name'], data['age'])

Person.from_string("Alice,30")
# p2 = Person.from_dict({"name": "Bob", "age": 25})
p1 = Person

print(p1.name, p1.age)