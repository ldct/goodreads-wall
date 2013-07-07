import urllib

result = urllib.urlopen('https://www.googleapis.com/books/v1/volumes?q=isbn%3A(1416903372+OR+0060510862+OR+0060838582+OR+0743455967)')
print result.readlines()