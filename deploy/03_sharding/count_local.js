// 任务六：计数（直连分片或 mongos 均可执行）
const lib = db.getSiblingDB("library");
print("borrow_logs = " + lib.borrow_logs.countDocuments({}) +
      "   books = " + lib.books.countDocuments({}) +
      "   readers = " + lib.readers.countDocuments({}));
